import importlib
import importlib.util
from pathlib import Path


def service():
    assert importlib.util.find_spec('render') is not None, 'shared render services must exist'
    return importlib.import_module('render.ffmpeg')


def test_resolver_priority_and_invalid_env_fallback(tmp_path, monkeypatch):
    ff = service()
    paths = [tmp_path / name for name in ('env.exe', 'path.exe', 'ffmpeg.exe', 'config.exe')]
    for p in paths:
        p.write_bytes(b'binary')
    monkeypatch.setenv('FFMPEG_EXE', str(paths[0]))
    monkeypatch.setattr(ff.shutil, 'which', lambda name: str(paths[1]))
    assert ff.find_ffmpeg(bundled_root=tmp_path, configured_path=paths[3]) == str(paths[0])
    monkeypatch.setenv('FFMPEG_EXE', str(tmp_path / 'missing'))
    assert ff.find_ffmpeg(bundled_root=tmp_path, configured_path=paths[3]) == str(paths[1])
    monkeypatch.setattr(ff.shutil, 'which', lambda name: None)
    assert ff.find_ffmpeg(bundled_root=tmp_path, configured_path=paths[3]) == str(paths[2])
    paths[2].unlink()
    assert ff.find_ffmpeg(bundled_root=tmp_path, configured_path=paths[3]) == str(paths[3])
    paths[3].unlink()
    assert ff.find_ffmpeg(bundled_root=tmp_path) is None


def test_encoder_fallback_retries_cpu_and_surfaces_cpu_failure(monkeypatch):
    ff = service()
    commands = []
    def run(cmd, duration_seconds, progress_start=92.0, progress_end=100.0):
        commands.append(cmd)
        if 'h264_nvenc' in cmd:
            raise ff.subprocess.CalledProcessError(1, cmd)
    monkeypatch.setattr(ff, 'ffmpeg_has_nvenc', lambda exe: True)
    monkeypatch.setattr(ff, 'run_ffmpeg_with_progress', run)
    ff.encode_video('ffmpeg', 'silent.mp4', 'audio.wav', 'out.mp4', 10)
    assert len(commands) == 2
    assert 'h264_nvenc' in commands[0]
    assert 'libx264' in commands[1]
    assert 'aac' in commands[1]
    assert commands[1].count('-i') == 2


def test_silent_export_still_encodes_h264(monkeypatch):
    ff = service()
    commands = []
    monkeypatch.setattr(ff, 'ffmpeg_has_nvenc', lambda exe: False)
    monkeypatch.setattr(ff, 'run_ffmpeg_with_progress', lambda cmd, *a, **kw: commands.append(cmd))
    ff.encode_video('ffmpeg', 'silent.mp4', None, 'out.mp4', 2)
    assert commands[0].count('-i') == 1
    assert 'libx264' in commands[0]
    assert '-an' in commands[0]


def test_fast_encode_uses_faster_preset_without_changing_default(monkeypatch):
    ff = service(); commands=[]
    monkeypatch.setattr(ff, 'ffmpeg_has_nvenc', lambda exe: True)
    monkeypatch.setattr(ff, 'run_ffmpeg_with_progress', lambda cmd, *a, **kw: commands.append(cmd))
    ff.encode_video('ffmpeg','silent.mp4','audio.wav','out.mp4',2,fast=True)
    assert commands[0][commands[0].index('-preset')+1]=='p4'
