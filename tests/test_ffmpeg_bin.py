"""Resolución de ffmpeg/ffprobe y extracción de fotogramas sin binario en PATH."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.exercise_analysis import AnalysisError, extract_audio_wav, extract_keyframes
from app.exercise_uploads import probe_video_duration
from app.ffmpeg_bin import parse_ffmpeg_duration, reset_ffmpeg_cache, resolve_ffmpeg, resolve_ffprobe


@pytest.fixture(autouse=True)
def _clear_ffmpeg_cache():
    reset_ffmpeg_cache()
    yield
    reset_ffmpeg_cache()


def test_parse_ffmpeg_duration_from_stderr():
    stderr = (
        "Input #0, mov,mp4,mp4a:\n"
        "  Duration: 00:00:12.48, start: 0.000000, bitrate: 1234 kb/s\n"
    )
    assert parse_ffmpeg_duration(stderr) == pytest.approx(12.48)


def test_resolve_ffmpeg_prefers_env_path(tmp_path, monkeypatch):
    bin_path = tmp_path / "ffmpeg"
    bin_path.write_text("#!/bin/sh\n")
    bin_path.chmod(0o755)
    monkeypatch.setenv("FFMPEG_PATH", str(bin_path))
    monkeypatch.setattr("app.ffmpeg_bin.shutil.which", lambda _name: "/usr/bin/ffmpeg")
    assert resolve_ffmpeg() == str(bin_path)


def test_resolve_ffmpeg_falls_back_to_imageio(monkeypatch):
    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    monkeypatch.setattr("app.ffmpeg_bin.shutil.which", lambda _name: None)
    monkeypatch.setattr("app.ffmpeg_bin._imageio_ffmpeg_exe", lambda: "/bundled/ffmpeg")
    assert resolve_ffmpeg() == "/bundled/ffmpeg"


def test_resolve_ffmpeg_raises_when_unavailable(monkeypatch):
    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    monkeypatch.setattr("app.ffmpeg_bin.shutil.which", lambda _name: None)
    monkeypatch.setattr("app.ffmpeg_bin._imageio_ffmpeg_exe", lambda: None)
    with pytest.raises(FileNotFoundError, match="ffmpeg"):
        resolve_ffmpeg()


def test_resolve_ffprobe_uses_sibling_of_ffmpeg(tmp_path, monkeypatch):
    monkeypatch.delenv("FFPROBE_PATH", raising=False)
    monkeypatch.setattr("app.ffmpeg_bin.shutil.which", lambda _name: None)
    ffmpeg = tmp_path / "ffmpeg"
    ffprobe = tmp_path / "ffprobe"
    ffmpeg.write_text("#!/bin/sh\n")
    ffprobe.write_text("#!/bin/sh\n")
    ffmpeg.chmod(0o755)
    ffprobe.chmod(0o755)
    monkeypatch.setenv("FFMPEG_PATH", str(ffmpeg))
    assert resolve_ffprobe() == str(ffprobe)


def test_extract_keyframes_uses_resolved_binary(tmp_path, monkeypatch):
    monkeypatch.setattr("app.exercise_analysis.resolve_ffmpeg", lambda: "/opt/resolved/ffmpeg")

    captured: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        captured.append(list(cmd))
        dest = Path(cmd[-1]).parent
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "frame_001.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        return SimpleNamespace(returncode=0, stderr=b"", stdout=b"")

    monkeypatch.setattr("app.exercise_analysis.subprocess.run", fake_run)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"ftyp")
    frames = extract_keyframes(video, tmp_path / "frames", duration=3.0)
    assert captured
    assert captured[0][0] == "/opt/resolved/ffmpeg"
    assert len(frames) == 1


def test_extract_keyframes_falls_back_to_first_frame(tmp_path, monkeypatch):
    monkeypatch.setattr("app.exercise_analysis.resolve_ffmpeg", lambda: "/opt/resolved/ffmpeg")
    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        calls.append(list(cmd))
        dest = Path(cmd[-1]).parent
        dest.mkdir(parents=True, exist_ok=True)
        if any(arg.startswith("fps=") or (arg == "-vf") for arg in cmd):
            return SimpleNamespace(returncode=1, stderr=b"Invalid fps", stdout=b"")
        (dest / "frame_001.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        return SimpleNamespace(returncode=0, stderr=b"", stdout=b"")

    monkeypatch.setattr("app.exercise_analysis.subprocess.run", fake_run)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"ftyp")
    frames = extract_keyframes(video, tmp_path / "frames", duration=4.0)
    assert len(frames) == 1
    assert any("-vf" in c for c in calls)
    assert any(c.count("-frames:v") and "1" in c for c in calls)


def test_extract_keyframes_missing_binary_is_analysis_error(tmp_path, monkeypatch):
    def boom():
        raise FileNotFoundError("ffmpeg no está disponible")

    monkeypatch.setattr("app.exercise_analysis.resolve_ffmpeg", boom)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"ftyp")
    with pytest.raises(AnalysisError, match="fotogramas"):
        extract_keyframes(video, tmp_path / "frames", duration=2.0)


def test_probe_duration_falls_back_to_ffmpeg_stderr(tmp_path, monkeypatch):
    monkeypatch.setattr("app.exercise_uploads.resolve_ffprobe", lambda: None)
    monkeypatch.setattr("app.exercise_uploads.resolve_ffmpeg", lambda: "/opt/resolved/ffmpeg")

    def fake_run(cmd, **_kwargs):
        assert cmd[0] == "/opt/resolved/ffmpeg"
        return SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="Duration: 00:00:08.00, start: 0.000000, bitrate: 800 kb/s\n",
        )

    monkeypatch.setattr("app.exercise_uploads.subprocess.run", fake_run)
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    assert probe_video_duration(clip) == pytest.approx(8.0)


def test_extract_audio_uses_resolved_ffmpeg(tmp_path, monkeypatch):
    monkeypatch.setattr("app.exercise_analysis.resolve_ffmpeg", lambda: "/opt/resolved/ffmpeg")

    def fake_run(cmd, **_kwargs):
        assert cmd[0] == "/opt/resolved/ffmpeg"
        dest = Path(cmd[-1])
        dest.write_bytes(b"RIFF" + b"\x00" * 80)
        return SimpleNamespace(returncode=0, stderr=b"", stdout=b"")

    monkeypatch.setattr("app.exercise_analysis.subprocess.run", fake_run)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"ftyp")
    wav = extract_audio_wav(video, tmp_path / "audio.wav")
    assert wav is not None
    assert wav.is_file()
