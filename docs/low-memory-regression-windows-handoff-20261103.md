# Low-memory regression + Windows acceptance handoff (2026-11-03)

## Verdict
**RENDER_REGRESSION_PASS / WINDOWS_REAL_DEVICE_NOT_RUN**

This document records a **real** Render test run against GitHub revision `162a53d397112d9c3a5baac388555cadd944de36`. It does **not** claim Windows was tested or that the full commercial video product is production-ready.

| Gate | Result | Exact evidence |
| --- | --- | --- |
| Existing local renderer & SRT smoke | **PASS 5/5** | `scripts/offline_smoke.py`; Render logs around 2026-11-03T16:08:26Z |
| New low-memory regression suite | **PASS 9/9** | `python -m unittest test.services.test_ffmpeg_low_memory -v`; Render logs **2026-11-03T16:09:54Z**: `Ran 9 tests in 10.579s`, `OK`, `MPT_LOW_MEMORY_REGRESSION_RESULT=PASS` |
| Real local-source FastAPI → task → MP4 → HTTP download | **PASS 4/4 at 480×480** | Render logs **2026-11-03T16:10:34Z**, `MPT_API_OFFLINE_E2E_RESULT` status PASS; `MPT_API_E2E_RESOLUTION=480`, `MPT_API_E2E_LOW_MEMORY=1`, source 540×540 |
| 1080p low-memory Render E2E | **Previously PASS 4/4** | Separate tested SHA `aeb2ea0db8406d1bf1e2c777738ada547e52feb8`, see `docs/1080p-low-memory-real-e2e-20261103.md`. New regression-only commits have **not** re-run 1080p. |
| **Windows 11 real-device 1080p** | **NOT_RUN** | PowerShell entry exists but has not been run on Windows |

## GitHub delivery
- Branch: `dev/mpt-slim-20261103` (main untouched)
- `test/services/test_ffmpeg_low_memory.py`: 9 regression tests, including opt-in-only selection, fallback for transitions/multi-source/speed/short footage, fallback for captions/BGM, atomic failure protection, actual tiny FFmpeg + audio mux.
- `scripts/accept-low-memory-windows.ps1`: Windows-only gate that demands branch, Python, FFmpeg/FFprobe; runs **9 regression tests → 5 standalone smoke checks → 4 real FastAPI HTTP checks** at 1080×1080 (540×540 local fixture); outputs logs and `evidence/mpt-low-memory-windows-gate.json`. No paid AI API calls, Docker or GitHub Actions, and no automatic package installation.
- `scripts/offline_smoke.py`: when Render's `MPT_API_E2E=1` is explicitly enabled, now requires regression suite PASS before invoking real API E2E.

## Windows run, only after a real branch checkout with dependencies installed
From Windows PowerShell, in the checked-out repository:
```powershell
powershell -NoProfile -File .\scripts\accept-low-memory-windows.ps1
```
If the machine lacks Python, FFmpeg/FFprobe or installed project requirements, the script reports a blocker/failure and saves evidence; do not interpret this as PASS. Windows is **not yet accepted**.

## Limits and operational caution
- New tests do not validate 9:16, 16:9, captions burned into frames, background music, transitions, long videos, real vocals, actual external H3/LLM/TTS calls or Windows codecs.
- Render's **web service** is used as a one-shot test runner: the CLI exits without listening for an HTTP port, so Render can label deployments unhealthy; test outcome is determined from logged checks, not deployment health.
- Evidence document commit is newer than the exact tested SHA.
