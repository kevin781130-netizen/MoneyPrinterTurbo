# Offline smoke execution evidence — 2026-11-03

Repository: `kevin781130-netizen/MoneyPrinterTurbo`
Branch: `dev/mpt-slim-20261103`
Classification: **ENVIRONMENT_BLOCKED** (full project smoke not executed).

## Executed in isolated Linux runtime

| Check | Outcome | Evidence |
| --- | --- | --- |
| Python compilation of `scripts/offline_smoke.py` content | **PASS** | `python -m py_compile` completed |
| `ffmpeg`, `ffprobe` tools | **PASS** | Both found under `/usr/bin`; FFmpeg 7.1.5, `libx264` encoder available |
| Native FFmpeg video+audio output | **PASS (prerequisite only)** | Generated 160x90 H.264 MP4 with AAC audio, `ffprobe` duration 0.700000 seconds, both streams present |
| **Actual** project `VideoProject` + SRT workflow | **ENVIRONMENT_BLOCKED** | Running smoke without checked-out project returned `No module named 'app'`, exit code 2 |

### Interpretation

The native FFmpeg result demonstrates that the runtime can encode/decode the smoke fixture; **it is not a PASS for the project's VideoProject implementation or SRT writer**. It did not execute the actual `/videos` task pipeline either.

The GitHub connector allowed a read-only review of the project's source, but this isolated execution environment had **no checked-out `app/` tree** and its outbound GitHub fetch failed DNS resolution. No fake stand-ins or copied substitute renderer were counted as passing product tests. No evidence of a code defect has been established by these checks.

### Safe next verification gate

Run `python scripts/offline_smoke.py --json-out evidence/mpt-offline-smoke.json` **from an actual checked-out copy of this branch** with Python, `loguru`, FFmpeg and FFprobe present. Review the output, require `status: PASS` with all 5 checks before claiming the local renderer gate passed. Continue to hold the full product/HTTP/paid-provider acceptance as NOT_RUN.

No Docker, GitHub Actions, external paid calls, or changes to `main` occurred.
