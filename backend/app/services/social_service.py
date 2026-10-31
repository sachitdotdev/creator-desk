"""Social channel publishing adapters.

Creator Desk runs fully locally and does not ship real platform API
integrations, so publishing here is *simulated*: the schedule is marked
``posted`` and a mock post URL is returned. The adapter structure makes it
straightforward to wire real TikTok / YouTube / Instagram APIs later
(just swap ``_publish`` for an authenticated API call per platform).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app import models

logger = logging.getLogger("creatordesk.social")

SUPPORTED_PLATFORMS = ("youtube", "tiktok", "instagram")


class SocialService:
    def post_schedule(self, db, schedule: models.Schedule) -> dict:
        """Publish a single scheduled clip to its target channel."""
        clip = db.query(models.Clip).filter(models.Clip.id == schedule.clip_id).first()
        if not clip:
            raise ValueError("Clip not found")
        if clip.status not in ("rendered", "approved"):
            raise ValueError(f"Clip is not ready to post (status: {clip.status})")

        account: Optional[models.SocialAccount] = None
        if schedule.account_id:
            account = (
                db.query(models.SocialAccount)
                .filter(models.SocialAccount.id == schedule.account_id)
                .first()
            )
        if account is None:
            account = (
                db.query(models.SocialAccount)
                .filter(
                    models.SocialAccount.platform == schedule.platform,
                    models.SocialAccount.status == "connected",
                )
                .first()
            )
        if account is None or account.status != "connected":
            raise ValueError(f"No connected {schedule.platform} account")

        post_url = self._publish(account, clip)

        schedule.status = "posted"
        schedule.posted_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(schedule)

        logger.info(
            "Posted clip %s to %s (%s) -> %s",
            clip.id,
            account.platform,
            account.account_name,
            post_url,
        )
        return {
            "platform": account.platform,
            "account": account.account_name,
            "post_url": post_url,
            "simulated": True,
        }

    def _publish(self, account: models.SocialAccount, clip: models.Clip) -> str:
        """Simulate publishing to the platform. Replace with real API calls."""
        handle = account.channel_id or account.account_name
        return f"https://{account.platform}.com/{handle}/post/clip_{clip.id}"
