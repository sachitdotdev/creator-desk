"""Automated short-form lead finder built on yt-dlp.

Discovers YouTube Shorts candidates from keyword searches or channel
handles (for example ``"podcast clips"``, ``"reddit stories"``,
``"scifi facts"`` or ``@ChannelHandle``), ranks them by view velocity
(view count / hours since upload) within the last 72 hours, and persists
the top candidates to ``backend/leads.json`` so they can be reviewed and
approved for processing through ``POST /api/process-lead``.

The initial listing uses ``extract_flat=True`` so only search/tab metadata
is fetched -- no media is downloaded. upload_date is not available in flat
extraction, so it is filled in with a lightweight per-video metadata
extraction (download=False) for the most promising candidates.
"""
from __future__ import annotations

import concurrent.futures
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yt_dlp
from yt_dlp.utils import DownloadError

from app.core.config import BASE_DIR, SOURCES_DIR

logger = logging.getLogger("creatordesk.lead_finder")

DEFAULT_QUERIES: List[str] = ["podcast clips", "reddit stories", "scifi facts"]
MAX_PER_QUERY = 20
# upload_date is missing in flat extraction, so only the most-viewed shorts
# candidates get an individual metadata fetch to keep the run fast.
MAX_INDIVIDUAL_FETCHES = 40
FETCH_WORKERS = 4
HORIZON_HOURS = 72
TOP_N = 10
# YouTube Shorts are <= 60 seconds. Entries without a known duration are kept
# (best effort) so a missing field never silently drops every candidate.
SHORTS_MAX_DURATION_SECONDS = 60

LEADS_PATH = BASE_DIR / "leads.json"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_upload_date(raw: Any) -> Optional[datetime]:
    """Parse yt-dlp ``upload_date`` (YYYYMMDD) or ``timestamp`` (unix secs)."""
    if raw is None:
        return None
    try:
        if isinstance(raw, (int, float)):
            return datetime.fromtimestamp(float(raw), tz=timezone.utc)
        text = str(raw).strip()
        if len(text) == 8 and text.isdigit():
            return datetime.strptime(text, "%Y%m%d").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
    return None


class LeadFinderService:
    def __init__(
        self,
        leads_path: str | Path = LEADS_PATH,
        horizon_hours: int = HORIZON_HOURS,
        top_n: int = TOP_N,
    ):
        self.leads_path = Path(leads_path)
        self.horizon_hours = horizon_hours
        self.top_n = top_n

    # ------------------------------------------------------------------ public
    def find_leads(
        self,
        queries: Optional[Iterable[str]] = None,
        max_per_query: int = MAX_PER_QUERY,
    ) -> List[Dict[str, Any]]:
        """Search every query, rank by view velocity, persist top N to leads.json."""
        query_list = list(queries) if queries is not None else list(DEFAULT_QUERIES)

        # 1. Fast flat listing: URL, title, view_count, duration -- no downloads.
        raw_candidates: List[Dict[str, Any]] = []
        for query in query_list:
            try:
                raw_candidates.extend(self._list_query(query, max_per_query))
            except Exception as exc:  # one bad query must not abort the run
                logger.warning("Lead finder query %r failed: %s", query, exc)

        # 2. Keep short-form candidates only.
        shorts = [
            c
            for c in raw_candidates
            if c.get("duration") is None or c["duration"] <= SHORTS_MAX_DURATION_SECONDS
        ]

        # 3. upload_date is unavailable in flat extraction: fetch it
        #    individually for the most-viewed shorts candidates.
        shorts.sort(key=lambda c: int(c.get("view_count") or 0), reverse=True)
        fetched = self._fetch_upload_dates(shorts[:MAX_INDIVIDUAL_FETCHES])
        fetched_ids = {c.get("id") for c in fetched if c.get("id")}
        candidates = fetched + [c for c in shorts if c.get("id") not in fetched_ids]

        # 4. Rank: uploaded within the last 72 hours, by view velocity
        #    (view count / hours since publication).
        leads = self._rank(candidates)

        # 5. Persist top N for the user to review in leads.json.
        self._save_leads(leads)
        return leads

    @staticmethod
    def load_leads(leads_path: str | Path = LEADS_PATH) -> List[Dict[str, Any]]:
        path = Path(leads_path)
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to read %s: %s", path, exc)
            return []
        return data if isinstance(data, list) else []

    @staticmethod
    def find_lead_by_url(
        url: str, leads_path: str | Path = LEADS_PATH
    ) -> Optional[Dict[str, Any]]:
        for lead in LeadFinderService.load_leads(leads_path):
            if lead.get("url") == url:
                return lead
        return None

    @staticmethod
    def mark_lead_processed(
        url: str,
        output_path: str,
        leads_path: str | Path = LEADS_PATH,
    ) -> None:
        """Mark a lead as processed in leads.json (best effort)."""
        path = Path(leads_path)
        if not path.exists():
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                leads = json.load(f)
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(leads, list):
            return
        changed = False
        for lead in leads:
            if lead.get("url") == url:
                lead["status"] = "processed"
                lead["output_path"] = output_path
                lead["processed_at"] = _utc_now().isoformat()
                changed = True
        if changed:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(leads, f, ensure_ascii=False, indent=2)
            except OSError as exc:
                logger.warning("Failed to write %s: %s", path, exc)

    # ------------------------------------------------------------------ download
    def download_lead(self, url: str, out_dir: str | Path = SOURCES_DIR) -> Tuple[Path, str]:
        """Download a lead video with yt-dlp. Returns (local path, title)."""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_tmpl = str(out_dir / "lead_%(id)s.%(ext)s")
        ydl_opts: Dict[str, Any] = {
            "format": (
                "bv*[height<=1080][ext=mp4]+ba[ext=m4a]"
                "/b[height<=1080][ext=mp4]"
                "/bv*+ba/b"
            ),
            "outtmpl": out_tmpl,
            "merge_output_format": "mp4",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        video_id = info.get("id")
        matches = list(out_dir.glob(f"lead_{video_id}.*")) if video_id else []
        if not matches:
            matches = [Path(ydl.prepare_filename(info))]
        local_path = matches[0]
        title = info.get("title") or local_path.name
        return local_path, str(title)

    # ---------------------------------------------------------------- listing
    def _list_query(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        q = query.strip()
        if q.startswith(("http://", "https://")):
            url = q
        elif q.startswith("@"):
            url = f"https://www.youtube.com{q}"
        elif "youtube.com" in q or "/@" in q:
            url = q if q.startswith("http") else "https://" + q
        else:
            url = f"ytsearch{max_results}:{q}"

        ydl_opts: Dict[str, Any] = {
            "extract_flat": True,
            "quiet": True,
            "no_warnings": True,
            "extractor_retries": 1,
            "retries": 1,
            "socket_timeout": 25,
        }
        if "ytsearch" not in url:
            ydl_opts["playlistend"] = max_results

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        entries: List[Dict[str, Any]] = []
        if not info:
            return entries
        if info.get("_type") == "video" and not info.get("entries"):
            raw_entries = [info]
        else:
            raw_entries = info.get("entries") or []

        for e in raw_entries:
            if not e or e.get("_type") == "url":
                continue
            video_id = e.get("id") or (e.get("url") or "").rsplit("v=", 1)[-1]
            if not video_id:
                continue
            entries.append(
                {
                    "id": video_id,
                    "title": e.get("title") or "",
                    "url": e.get("url") or f"https://www.youtube.com/watch?v={video_id}",
                    "channel": e.get("channel") or e.get("uploader") or "",
                    "duration": e.get("duration"),
                    "view_count": e.get("view_count"),
                    "_query": q,
                }
            )
        return entries

    # ---------------------------------------------------------------- metadata
    def _fetch_one(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Individually extract one video page to fill in upload_date."""
        ydl_opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "extractor_retries": 1,
            "retries": 1,
            "socket_timeout": 25,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(entry["url"], download=False)

        merged = dict(entry)
        if info.get("upload_date"):
            merged["upload_date"] = info.get("upload_date")
        if info.get("timestamp") is not None:
            merged["timestamp"] = info.get("timestamp")
        if info.get("view_count") is not None:
            merged["view_count"] = info.get("view_count")
        if info.get("channel"):
            merged["channel"] = info.get("channel")
        if info.get("duration") is not None:
            merged["duration"] = info.get("duration")

        uploaded = _parse_upload_date(
            merged.get("upload_date") or merged.get("timestamp")
        )
        merged["_uploaded"] = uploaded
        merged["_uploaded_iso"] = uploaded.isoformat() if uploaded else None
        return merged

    def _fetch_upload_dates(
        self, entries: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        if not entries:
            return []
        results: List[Dict[str, Any]] = []
        workers = min(FETCH_WORKERS, len(entries))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self._fetch_one, e): e for e in entries}
            for future in concurrent.futures.as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as exc:  # skip videos we cannot inspect
                    logger.warning("Lead metadata fetch failed: %s", exc)
        return results

    # ---------------------------------------------------------------- ranking
    def _rank(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        now = _utc_now()
        scored: List[Tuple[float, Dict[str, Any], float]] = []
        for entry in entries:
            uploaded = entry.get("_uploaded")
            if not uploaded:
                continue
            hours = (now - uploaded).total_seconds() / 3600.0
            if hours < 0.0 or hours > self.horizon_hours:
                continue
            views = int(entry.get("view_count") or 0)
            velocity = views / max(hours, 1.0)
            scored.append((velocity, entry, hours))

        scored.sort(key=lambda item: item[0], reverse=True)
        leads: List[Dict[str, Any]] = []
        for velocity, entry, hours in scored[: self.top_n]:
            leads.append(
                {
                    "url": entry["url"],
                    "title": entry.get("title") or "",
                    "channel": entry.get("channel") or "",
                    "view_count": int(entry.get("view_count") or 0),
                    "upload_date": entry.get("upload_date") or "",
                    "uploaded_at": entry.get("_uploaded_iso") or "",
                    "hours_since_upload": round(hours, 2),
                    "view_velocity": round(velocity, 2),
                    "source_query": entry.get("_query") or "",
                    "duration": entry.get("duration"),
                    "status": "pending",
                    "recommended_at": now.isoformat(),
                }
            )
        return leads

    # ---------------------------------------------------------------- persistence
    def _save_leads(self, leads: List[Dict[str, Any]]) -> None:
        self.leads_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.leads_path, "w", encoding="utf-8") as f:
            json.dump(leads, f, ensure_ascii=False, indent=2)
        logger.info("Wrote %d lead(s) to %s", len(leads), self.leads_path)
