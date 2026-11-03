"""Regression gates for opt-in low-RAM FFmpeg renderer.

python -m unittest test.services.test_ffmpeg_low_memory -v
No remote services, Docker, secrets or GitHub Actions. Native FFmpeg tests use
tiny synthetic fixtures and do not prove production multi-minute workloads.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import wave
from unittest.mock import Mock, patch

from app.config import config
from app.services import ffmpeg_low_memory as lowmem
from app.services import video
from app.models.schema import VideoParams


class _Audio:
    duration = 3.0

    def close(self):
        pass


class TestLowMemorySelection(unittest.TestCase):
    def setUp(self):
        self.saved = dict(config.app)
        config.app["low_memory_ffmpeg_mode"] = False

    def tearDown(self):
        config.app.clear()
        config.app.update(self.saved)

    def _combine(self, **overrides):
        kwargs = dict(
            combined_video_path="combined.mp4", video_paths=["source.mp4"],
            audio_file="narration.mp3", video_aspect="1:1",
            video_transition_mode=None, max_clip_duration=5,
            clip_speed=1.0, threads=1,
        )
        kwargs.update(overrides)
        return video.combine_videos(**kwargs)

    def test_default_is_legacy_even_for_eligible_single_source(self):
        with (
            patch.object(video, "AudioFileClip", return_value=_Audio()),
            patch.object(lowmem, "source_duration") as duration_probe,
            patch.object(lowmem, "combine_one_source") as fast,
            patch.object(video, "_open_video_clip_quietly", side_effect=RuntimeError("legacy decoder")) as legacy,
        ):
            with self.assertRaisesRegex(RuntimeError, "no readable video clips"):
                self._combine()
            legacy.assert_called()
            duration_probe.assert_not_called()
            fast.assert_not_called()

    def test_enabled_valid_one_clip_uses_streaming_renderer(self):
        config.app["low_memory_ffmpeg_mode"] = True
        used = []
        cb = Mock()
        with (
            patch.object(video, "AudioFileClip", return_value=_Audio()),
            patch.object(lowmem, "source_duration", return_value=4.5),
            patch.object(lowmem, "combine_one_source", return_value="combined.mp4") as fast,
            patch.object(video, "_open_video_clip_quietly") as legacy,
        ):
            result = self._combine(used_video_paths=used, progress_callback=cb)
            self.assertEqual(result, "combined.mp4")
            self.assertEqual(used, ["source.mp4"])
            fast.assert_called_once()
            self.assertEqual(fast.call_args.kwargs["width"], 1080)
            cb.assert_called_once()
            legacy.assert_not_called()

    def test_unsupported_settings_never_use_streaming(self):
        config.app["low_memory_ffmpeg_mode"] = True
        cases = [
            {"video_paths": ["a.mp4", "b.mp4"]},
            {"clip_speed": 0.5},
            {"video_transition_mode": "FadeIn"},
            {"max_clip_duration": 2},
        ]
        for case in cases:
            with self.subTest(case=case), (
                patch.object(video, "AudioFileClip", return_value=_Audio()),
                patch.object(lowmem, "combine_one_source") as fast,
                patch.object(video, "_open_video_clip_quietly", side_effect=RuntimeError("legacy decoder")) as legacy,
            ):
                with self.assertRaisesRegex(RuntimeError, "no readable video clips"):
                    self._combine(**case)
                legacy.assert_called()
                fast.assert_not_called()

    def test_too_short_source_uses_existing_renderer(self):
        config.app["low_memory_ffmpeg_mode"] = True
        with (
            patch.object(video, "AudioFileClip", return_value=_Audio()),
            patch.object(lowmem, "source_duration", return_value=1.1),
            patch.object(lowmem, "combine_one_source") as fast,
            patch.object(video, "_open_video_clip_quietly", side_effect=RuntimeError("legacy decoder")),
        ):
            with self.assertRaisesRegex(RuntimeError, "no readable video clips"):
                self._combine()
            fast.assert_not_called()

    def _final(self, **params_override):
        opts = dict(video_subject="offline", subtitle_enabled=False,
                    bgm_type="none", bgm_volume=0)
        opts.update(params_override)
        return video.generate_video(
            "combined.mp4", "voice.wav", "", "final.mp4", VideoParams(**opts)
        )

    def test_dry_narration_uses_low_ram_mux_only_when_enabled(self):
        config.app["low_memory_ffmpeg_mode"] = True
        with (
            patch.object(lowmem, "mux_dry_voiceover") as mux,
            patch.object(video, "_open_video_clip_quietly") as legacy,
        ):
            self.assertTrue(self._final())
            mux.assert_called_once()
            legacy.assert_not_called()

    def test_subtitles_bgm_and_default_mode_fall_back_to_moviepy(self):
        cases = [
            (False, {}),
            (True, {"subtitle_enabled": True}),
            (True, {"bgm_type": "custom", "bgm_volume": 0.2}),
        ]
        for enabled, opts in cases:
            with self.subTest(enabled=enabled, opts=opts):
                config.app["low_memory_ffmpeg_mode"] = enabled
                with (
                    patch.object(lowmem, "mux_dry_voiceover") as mux,
                    patch.object(video, "_open_video_clip_quietly", side_effect=RuntimeError("legacy renderer")) as legacy,
                    patch.object(video.file_security, "resolve_path_within_directory", return_value="safe-font.ttf"),
                ):
                    with self.assertRaisesRegex(RuntimeError, "legacy renderer"):
                        self._final(**opts)
                    legacy.assert_called_once()
                    mux.assert_not_called()


class TestLowMemoryAtomicity(unittest.TestCase):
    def test_failed_render_keeps_previously_published_mp4(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d, "final.mp4")
            target.write_bytes(b"previous intact artifact")
            with patch.object(lowmem, "_run", side_effect=RuntimeError("bad input")):
                with self.assertRaisesRegex(RuntimeError, "bad input"):
                    lowmem._atomic_render(str(target), ["ffmpeg"], "fixture")
            self.assertEqual(target.read_bytes(), b"previous intact artifact")
            self.assertEqual(list(Path(d).glob("*.lowmem-*.mp4")), [])

    def test_invalid_dimensions_fail_before_any_encoder(self):
        with patch.object(lowmem, "_atomic_render") as writer:
            with self.assertRaisesRegex(ValueError, "even dimensions"):
                lowmem.combine_one_source(
                    source="source.mp4", output_file="out.mp4", duration=1,
                    width=1079, height=1080, fit_mode="cover",
                )
            writer.assert_not_called()

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "native FFmpeg and FFprobe required")
    def test_native_upscale_then_mux_preserves_video_and_audio(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "source.mp4"
            combined = root / "combined.mp4"
            output = root / "final.mp4"
            audio = root / "voice.wav"
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-v", "error", "-nostdin", "-y",
                 "-f", "lavfi", "-i", "color=c=blue:s=480x480:r=10:d=1.25",
                 "-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuv420p",
                 str(source)], check=True, capture_output=True, timeout=45,
            )
            with wave.open(str(audio), "wb") as wavefile:
                wavefile.setnchannels(1)
                wavefile.setsampwidth(2)
                wavefile.setframerate(24000)
                wavefile.writeframes(b"\x00\x00" * 30000)
            lowmem.combine_one_source(
                source=str(source), output_file=str(combined), duration=1.1,
                width=960, height=960, fit_mode="cover",
            )
            lowmem.mux_dry_voiceover(
                input_video=str(combined), input_audio=str(audio),
                output_file=str(output), voice_volume=1,
            )
            stream_info = lowmem._probe(str(output))["streams"]
            self.assertTrue(any(s.get("codec_type") == "video"
                                and s.get("width") == 960
                                and s.get("height") == 960 for s in stream_info))
            self.assertTrue(any(s.get("codec_type") == "audio" for s in stream_info))
            self.assertGreater(output.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
