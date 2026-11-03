# MoneyPrinterTurbo — Real offline smoke test PASS (2026-11-03)

**Verdict: LOCAL_RENDERER_AND_SRT_SMOKE_PASS (5/5).**
This **does not** attest to full `/videos` HTTP E2E, LLM, TTS providers, stock retrieval, remote H3, burn-in captions, or Windows device testing. All of those remain **NOT_RUN**.

## Exact tested revision

- Repo: `kevin781130-netizen/MoneyPrinterTurbo`
- Branch: `dev/mpt-slim-20261103`
- Tested SHA: `605f69351964991f2699726b13b24abb7650fd41`
- Fix: add project root to `sys.path` in `scripts/offline_smoke.py` when executed as a file.
- Render free Python service: `srv-dbkvkeui0phs73bdtfjg` (`mpt-offline-smoke-20261103`)
- Deploy id: `dep-dbkvlfoae00c73c71bs0`
- Logs: Render Dashboard → service → Logs; `2026-11-03T15:17:49Z` (UTC)
- Command: `python scripts/offline_smoke.py --json-out /tmp/mpt-offline-smoke.json`
- Build: `python -m pip install --disable-pip-version-check --no-cache-dir loguru && python -m py_compile scripts/offline_smoke.py`

## Real output observed in Render logs

```json
{
  "status": "PASS",
  "scope": "local-renderer-and-srt-only",
  "checks": [
    "native MP4 render and checksum",
    "video/audio streams and duration",
    "render stage cache",
    "atomic SRT publish and invalid-cue rejection",
    "corrupt input fails closed with persisted failure state"
  ]
}
```

## Interpretation / deployment status

Render successfully cloned SHA `605f6935`, built it using Python 3.11.18, and executed the repo's actual `VideoProject` and `subtitle_writer` modules. FFmpeg/FFprobe executed on generated media, without paid APIs, Docker, or GitHub Actions. Both success and intentional corrupted-input failure were checked.

After printing `status: PASS`, the one-shot CLI **exited normally rather than listening on an HTTP port**. Since the deployment target is a Render *web service*, Render subsequently emitted `Application exited early` and considers the service unhealthy. **This is a service-lifecycle mismatch, not a smoke-test failure**. Do not describe the Render web deployment itself as healthy or successful. To avoid a long-running service for testing, future executions should use a one-shot build/job runner instead.

## Remaining gates

- Main `/videos` API + end-to-end orchestration: NOT_RUN
- Existing provider-specific paid calls and H3 remote generation: NOT_RUN
- Subtitle actually burned onto MP4 by the product: NOT_RUN
- Windows real-machine verification: NOT_RUN

`main` is unchanged. Evidence file was committed after the tested SHA; new documentation commit is **not** the tested SHA.
