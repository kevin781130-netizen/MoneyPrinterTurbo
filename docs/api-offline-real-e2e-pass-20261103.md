# Real /videos API offline E2E — 2026-11-03

**Verdict: PASS — real HTTP -> queue -> local MoviePy/FFmpeg -> MP4 -> HTTP download, 4/4, TEST-ONLY 480×480.**

This is **not** a production-resolution pass. The original 1080×1080 run was killed by the Render Free instance's **512 MiB RAM limit** during MoviePy clip resizing. There is no basis from that run alone to label the product's 1080×1080 behavior defective.

## Exact test evidence
- GitHub repository: `kevin781130-netizen/MoneyPrinterTurbo`
- Branch: `dev/mpt-slim-20261103`
- **Tested code SHA:** `d48710c47e7b65bf28e5477596530bd824b944d7`
- Render service: `srv-dbkvkeui0phs73bdtfjg` (mpt-offline-smoke-20261103; Free / Python)
- Render deploy: `dep-dbkvuj15efls73fr7arg`
- Log timestamp: **2026-11-03 15:39:32 UTC**
- Log marker: `MPT_API_OFFLINE_E2E_RESULT=`
- Test command: `python scripts/api_offline_e2e.py --json-out /tmp/mpt-api-e2e-result.json`, invoked by existing `scripts/offline_smoke.py` when `MPT_API_E2E=1`
- `MPT_API_E2E_RESOLUTION=480`: test-only override of `VideoAspect.square.to_resolution()`; application source remains unchanged. This specifically excludes production 1080 resolution acceptance.
- Runtime: Python 3.11.18, existing Python-package requirements installed into an isolated virtual environment by `uv`. No Docker, no GitHub Actions.

## Observed result (exact fields)

```json
{
  "status": "PASS",
  "scope": "real-fastapi-local-source-no-paid-provider",
  "checks": [
    "real POST /api/v1/videos creates task",
    "real GET /api/v1/tasks/{id} reports completed 100%",
    "real MP4 has 480x480 video and audio (production resolution only if 1080)",
    "real GET /api/v1/download/{id}/final-1.mp4 matches output"
  ],
  "duration_seconds": 3.03,
  "width": 480,
  "production_resolution_tested": false,
  "height": 480,
  "output_bytes": 8067,
  "elapsed_seconds": 31.1
}
```

This actually calls the FastAPI `/api/v1/videos` route, real asynchronous task scheduler, script/audio/material/render pipeline, and HTTP status/download endpoints. A locally generated 540×540 blue video and user-supplied script were used, with the built-in `no-voice` silent MP3, `subtitle_enabled=false`, `bgm_volume=0`, `video_source=local`, and no external AI or media service. The renderer and API handlers were **not** stubbed.

## Limitations / remaining gates

- **1080×1080 production rendering**: ENVIRONMENT_BLOCKED on Render Free by 512 MiB OOM, NOT_PASS.
- **Rendered captions and Whisper**: NOT_RUN in this API E2E (earlier standalone SRT writer smoke did PASS).
- **Actual LLM/TTS/video-provider/H3 calls**: NOT_RUN. They would incur external or paid operations.
- **Windows real-device, longer content, concurrency, full feature acceptance**: NOT_RUN.
- Render Web Service itself is a one-shot test job and is expected to be marked unhealthy when it exits without opening an HTTP port. Its deployment health status is not equivalent to the test result.
- No modification of `main`; no product code changed. Evidence documentation commit comes *after* the tested SHA.
