
from pathlib import Path
import importlib
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("renderer_main_ffmpeg", ROOT / "main.py")
renderer_main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer_main)


def test_find_ffmpeg_finds_downloads_build(tmp_path):
    exe = tmp_path / "ffmpeg-9.0.1-essentials_build" / "bin" / "ffmpeg.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"fake")
    found = renderer_main.find_ffmpeg(search_root=tmp_path)
    assert found == str(exe)


def test_shared_ffmpeg_finds_current_users_downloads(tmp_path, monkeypatch):
    from render import ffmpeg
    exe = tmp_path / "Downloads" / "ffmpeg-9.0.1-essentials_build" / "bin" / "ffmpeg.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"fake")
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("FFMPEG_EXE", raising=False)
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda _name: None)
    assert ffmpeg.find_ffmpeg() == str(exe)


def test_every_render_entrypoint_uses_the_shared_ffmpeg_resolver():
    from render.ffmpeg import find_ffmpeg as shared_resolver
    modules=[renderer_main]
    modules.extend(importlib.import_module(f'engines.{path.stem}') for path in (ROOT/'engines').glob('*_engine.py'))
    assert modules
    assert all(getattr(module,'find_ffmpeg',None) is shared_resolver for module in modules)
