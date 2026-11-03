# MoneyPrinterTurbo 1080p opt-in low-memory FFmpeg acceptance — 2026-11-03

**Verdict: LIMITED_1080P_REAL_API_E2E_PASS.**

The **opt-in** low-RAM, single-source, no-transition, no-caption, no-BGM route produced a genuine **1080×1080 MP4 with an audio stream** in a Render Free Python instance capped at **512 MiB RAM**. Both matched-resolution **1080→1080** and rescaled **540→1080** inputs passed all 4 real FastAPI-TestClient checks at the **same exact code SHA**.

**Do not claim the full product, captions, multiple clips, high resolutions other than 1080×1080, or Windows hardware passed.**

## Exact tested revision

- Repo: `kevin781130-netizen/MoneyPrinterTurbo`
- Branch: `dev/mpt-slim-20261103`
- **Tested Git commit SHA: `aeb2ea0db8406d1bf1e2c777738ada547e52feb8`**
- Render service: `srv-dbkvkeui0phs73bdtfjg`, Python 3.11.18, Free plan
- No Docker, GitHub Actions or paid third-party generation API calls
- Endpoints exercised using FastAPI `TestClient`: `POST /api/v1/videos`, `GET /api/v1/tasks/{id}`, `GET /api/v1/download/{id}/final-1.mp4`
- Test script: `scripts/api_offline_e2e.py`; `MPT_API_E2E=1`, `MPT_API_E2E_RESOLUTION=1080`, `MPT_API_E2E_LOW_MEMORY=1`
- Product code changes: `app/services/ffmpeg_low_memory.py` and an explicit opt-in, narrow fast path in `app/services/video.py`; default `low_memory_ffmpeg_mode` is false.
- Tested output aspect: 1:1 (1080×1080); no user-uploaded custom audio, TTS, subtitles, BGM, transitions or provider assets involved. `voice_name=no-voice` creates silent WAV/MP3 locally as an audio stream.

## Baseline failures (same Render Free RAM constraint, original MoviePy path)

1. **540→1080**: Render OOM `Out of memory (used over 512Mi)` at **2026-11-03T15:34:37Z**, during MoviePy's clip resizing/processing.
2. **1080→1080**: Render OOM at **2026-11-03T15:46:40Z**, at MoviePy clip processing with **no resize**; therefore upscaling is *not* the sole cause.
3. Both OOMs are **ENVIRONMENT_BLOCKED at 512 MiB**, not proof of a product malfunction on adequately equipped machines.

## Low-memory real HTTP acceptance results

### Test A: 1080 source → 1080 MP4

- Render deploy: `dep-dbl055fb9u1s738jqd40`
- Completion log: **2026-11-03T15:53:03Z**
- `MPT_API_OFFLINE_E2E_RESULT`: status **PASS**
- Checks passed:
  - real `POST /api/v1/videos` creates an async task
  - real `GET /api/v1/tasks/{id}` reports completed 100%
  - real MP4 inspected by FFprobe contains 1080×1080 video and an audio stream
  - real HTTP file download matches the MP4 on disk
- Output 10,319 bytes, duration 3.034 seconds, test elapsed **19.98 seconds**
- `low_memory_ffmpeg_enabled: true`, `source_resolution: 1080`, `production_resolution_tested: true`

### Test B: 540 source → upscaled 1080 MP4

- Render deploy: `dep-dbl07461egvs73976i1g`
- Completion log: **2026-11-03T15:56:56Z**
- `MPT_API_OFFLINE_E2E_RESULT`: status **PASS**; same 4 checks
- Output 10,319 bytes, duration 3.034 seconds, test elapsed **14.49 seconds**
- `low_memory_ffmpeg_enabled: true`, `source_resolution: 540`, `width: 1080`, `height: 1080`, `production_resolution_tested: true`

## Exact fast-path guard and behavior

An explicitly enabled `config.app["low_memory_ffmpeg_mode"] = true` is necessary. Otherwise **existing MoviePy code remains the default**.

- Stream composition via FFmpeg is eligible only for **one valid video source**, normal `1.0x` playback, **no transition**, a source whose length covers the required narration timeline, and a single clip window large enough to cover it.
- The source clip is scaled/cropped or letterboxed with FFmpeg filters, tagged BT.709, encoded 30fps H.264 via `libx264` with one encoder thread, using a temporary MP4 and atomic publication.
- Final mux is eligible only when captions are disabled, BGM is disabled and no explicit BGM override exists. It stream-copies the prepared video and encodes the voice audio to AAC; it does not load 1080 RGB frames into Python.
- Unsupported effects and multi-source composition keep the original MoviePy implementation. This is a limited optimized path, not a general replacement.

## Gates still NOT_RUN

- Windows 11 real-machine acceptance, hardware codecs
- Normal 9:16 and 16:9 formats, multiscene editing/transition effects
- Subtitle burn-in and music mixing; multiple clips, short-source loops
- Real recorded voice tracks, audio level quality, colors/grading fidelity
- Multi-minute output, cancellation/concurrency, task upload
- Actual external AI generation, H3 or provider calls

The Render Web Service itself is configured as a **one-shot test runner**; after the test ends, it exits instead of listening on an HTTP port, so Render marks its deployment unhealthy. That is separate from the logged 4/4 API E2E result. For future tests, a one-shot worker/build job is preferable to an always-restarting Web Service.

`main` was not modified. This evidence document commit is newer than the tested SHA.
