# Credits

## Copying third-party code

When code under MIT, BSD, Apache-2.0, Unlicense or CC0 is copied into this
repository, the original copyright notice and license text must be kept verbatim
— either inline in a file header comment or in
`docs/third_party_licenses/<project>.txt`. For Apache-2.0 code, the original
`NOTICE` file content must also be preserved. Every copied file also needs a
header comment giving the source URL, license and copyright holder, plus a row
in this file (see the tables below). Ideas and techniques may be reimplemented
from understanding without copying, but unknown licenses mean do not copy.

## Used today

Dependencies and media actually used by the pipeline. Licenses were read from
installed package metadata on Nov 18, 2026 (see `docs/DEPENDENCY_LICENSES.md`).

| Project | License | Link | Use |
| --- | --- | --- | --- |
| faster-whisper | MIT | https://github.com/SYSTRAN/faster-whisper | transcription |
| Ultralytics YOLOv8 (`ultralytics`) | AGPL-3.0 | https://github.com/ultralytics/ultralytics | face detection (dependency only — its code is never copied) |
| FFmpeg | GPLv3 build (`--enable-gpl --enable-version3`, no `--enable-nonfree`; gyan.dev full build) | https://ffmpeg.org/ | all video/audio rendering |
| "Moon Over Red Dunes" (open-lofi, btahir) | CC0 1.0 Universal | https://github.com/btahir/open-lofi | BGM (`backend/assets/music/lofi.mp3`) |
| Anton font (The Anton Project Authors) | SIL Open Font License 1.1 | https://github.com/google/fonts/tree/main/ofl/anton | bundled condensed bold caption font (`backend/assets/fonts/Anton-Regular.ttf`, license text in `backend/assets/fonts/OFL.txt`) |
| OpenCV frontal-face cascade (Rainer Lienhart / Intel Corporation) | "Intel License Agreement For Open Source Computer Vision Library" (permissive terms retained in the file header) | https://github.com/opencv/opencv | data file (`backend/assets/models/haarcascade_frontalface_default.xml`); license text kept verbatim in the XML comment header |
| fastapi | MIT | https://github.com/fastapi/fastapi | backend API |
| uvicorn | BSD-3-Clause | https://github.com/encode/uvicorn | ASGI server |
| yt-dlp | Unlicense | https://github.com/yt-dlp/yt-dlp | media download |
| SQLAlchemy | MIT | https://www.sqlalchemy.org/ | database ORM |
| Alembic | MIT | https://alembic.sqlalchemy.org/ | database migrations |
| insanely-fast-whisper | MIT | https://github.com/Vaibhavs10/insanely-fast-whisper | transcription helper |
| PyAV (`av`) | BSD-3-Clause | https://github.com/PyAV-Org/PyAV | media probing |
| nvidia-cublas-cu12 | LicenseRef-NVIDIA-Proprietary | https://developer.nvidia.com/cuda-toolkit | CUDA runtime |
| nvidia-cudnn-cu12 | LicenseRef-NVIDIA-Proprietary | https://developer.nvidia.com/cudnn | CUDA runtime |
| aiofiles | Apache-2.0 | https://github.com/Tinche/aiofiles | async file I/O |
| OpenAI Python client (`openai`) | Apache-2.0 | https://github.com/openai/openai-python | vLLM chat completions client |
| python-multipart | Apache-2.0 | https://github.com/andrew-d/python-multipart | upload handling |
| httpx | BSD-3-Clause | https://github.com/encode/httpx | HTTP client |
| pydantic | MIT | https://github.com/pydantic/pydantic | schemas |
| python-dotenv | BSD-3-Clause | https://github.com/theskumar/python-dotenv | env loading |
| requests | Apache-2.0 | https://github.com/psf/requests | HTTP client |
| WhisperX | BSD-2-Clause (read LICENSE; sources disagree with BSD-4) | https://github.com/m-bain/whisperX | word-level timing |
| opencv-contrib-python | Apache-2.0 | https://opencv.org/ | frame capture |
| NumPy | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | https://numpy.org/ | numeric arrays |
| Accelerate | Apache-2.0 | https://github.com/huggingface/accelerate | model loading |
| React | MIT | https://react.dev/ | frontend |
| React DOM | MIT | https://react.dev/ | frontend |
| React Router | MIT | https://reactrouter.com/ | navigation |
| TanStack Query | MIT | https://tanstack.com/query | server state |
| axios | MIT | https://github.com/axios/axios | HTTP client |
| Vite | MIT | https://vite.dev/ | frontend build |
| TypeScript | Apache-2.0 | https://www.typescriptlang.org/ | frontend language |
| Tailwind CSS | MIT | https://tailwindcss.com/ | styling |
| Radix UI primitives | MIT | https://www.radix-ui.com/ | UI primitives |
| lucide-react | ISC | https://lucide.dev/ | icons |
| ESLint | MIT | https://eslint.org/ | frontend linting |

The remaining direct dependencies (frontend UI helpers and dev tooling) are
MIT, Apache-2.0 or ISC; the full list with versions and licenses is in
`docs/DEPENDENCY_LICENSES.md`.

## Inspiration and references

A row is added only when we actually read or use a project. Do not list projects
we have not used.

| Project | License | What we learned or used | Date |
| --- | --- | --- | --- |
