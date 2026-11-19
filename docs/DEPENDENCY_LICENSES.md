# Dependency licenses

Checked Nov 18, 2026. Backend licenses come from installed distribution metadata
(`importlib.metadata` in `backend/venv`), frontend licenses from each installed
package's `node_modules/<name>/package.json`. Flags: AGPL, GPL, LGPL, SSPL,
non-commercial, proprietary or unknown licenses. Direct dependencies only.

## Backend (`backend/requirements.txt`)

| Package | Version | License | Flag |
| --- | --- | --- | --- |
| fastapi | 0.163.1 | MIT | |
| uvicorn | 0.32.1 | BSD-3-Clause | |
| yt-dlp | 2026.10.26 | Unlicense | |
| SQLAlchemy | 2.0.29 | MIT | |
| Alembic | 1.13.2 | MIT | |
| insanely-fast-whisper | 0.0.15 | MIT | |
| PyAV (`av`) | 18.1.0 | BSD-3-Clause | |
| faster-whisper | 1.2.1 | MIT | |
| nvidia-cublas-cu12 | 12.9.2.10 | LicenseRef-NVIDIA-Proprietary | **FLAG — proprietary** |
| nvidia-cudnn-cu12 | 9.28.1.4 | LicenseRef-NVIDIA-Proprietary | **FLAG — proprietary** |
| aiofiles | 23.2.1 | Apache-2.0 | |
| OpenAI client (`openai`) | 3.51.0 | Apache-2.0 | |
| python-multipart | 0.0.9 | Apache-2.0 | |
| httpx | 0.28.1 | BSD-3-Clause | |
| pydantic | 2.14.3 | MIT | |
| python-dotenv | 1.0.1 | BSD-3-Clause | |
| requests | 2.34.2 | Apache-2.0 | |
| WhisperX | 3.8.6 | BSD-2-Clause | Note: sources disagree between BSD-2 and BSD-4; read the LICENSE file before relying on it. |
| opencv-contrib-python | 5.0.0.93 | Apache-2.0 | |
| NumPy | 2.5.5 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | |
| Ultralytics (`ultralytics`) | 8.4.214 | AGPL-3.0 | **FLAG — AGPL-3.0** (dependency only; never copy its code) |
| Accelerate | 1.15.0 | Apache | |

## Frontend (`frontend/package.json`)

| Package | Version | License | Flag |
| --- | --- | --- | --- |
| @radix-ui/react-avatar | 1.3.1 | MIT | |
| @radix-ui/react-checkbox | 1.4.1 | MIT | |
| @radix-ui/react-dialog | 1.3.1 | MIT | |
| @radix-ui/react-dropdown-menu | 2.2.1 | MIT | |
| @radix-ui/react-label | 2.1.17 | MIT | |
| @radix-ui/react-scroll-area | 1.4.0 | MIT | |
| @radix-ui/react-select | 2.4.1 | MIT | |
| @radix-ui/react-separator | 1.2.0 | MIT | |
| @radix-ui/react-slot | 1.5.0 | MIT | |
| @radix-ui/react-switch | 1.4.1 | MIT | |
| @radix-ui/react-tabs | 1.2.1 | MIT | |
| @tanstack/react-query | 5.105.0 | MIT | |
| @tanstack/react-query-devtools | 5.105.0 | MIT | |
| @types/uuid | 9.0.8 | MIT | |
| axios | 1.21.0 | MIT | |
| class-variance-authority | 0.7.1 | Apache-2.0 | |
| clsx | 2.1.1 | MIT | |
| cmdk | 1.1.1 | MIT | |
| date-fns | 3.6.0 | MIT | |
| embla-carousel-react | 8.6.0 | MIT | |
| lucide-react | 0.424.0 | ISC | |
| react | 18.3.1 | MIT | |
| react-dom | 18.3.1 | MIT | |
| react-hook-form | 7.91.0 | MIT | |
| react-router-dom | 6.30.6 | MIT | |
| sonner | 1.7.4 | MIT | |
| tailwind-merge | 2.6.1 | MIT | |
| uuid | 9.0.1 | MIT | |
| @eslint/js | 9.39.5 | MIT | |
| @types/react | 18.3.31 | MIT | |
| @types/react-dom | 18.3.7 | MIT | |
| @vitejs/plugin-react | 4.7.0 | MIT | |
| autoprefixer | 10.6.2 | MIT | |
| eslint | 9.39.5 | MIT | |
| eslint-plugin-react-hooks | 5.2.0 | MIT | |
| eslint-plugin-react-refresh | 0.4.26 | MIT | |
| globals | 15.15.0 | MIT | |
| postcss | 8.5.32 | MIT | |
| tailwindcss | 3.4.19 | MIT | |
| typescript | 5.9.3 | Apache-2.0 | |
| vite | 5.4.21 | MIT | |

No frontend dependency is flagged.

## FFmpeg build

`ffmpeg -version`: `9.0.2-full_build-www.gyan.dev`. The build configuration
contains `--enable-gpl` and `--enable-version3` and does **not** contain
`--enable-nonfree` — i.e. the build is GPLv3, not non-free. No AGPL/GPL source
is copied into this repository; FFmpeg is invoked as an external tool.
