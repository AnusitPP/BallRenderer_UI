
from pathlib import Path
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
