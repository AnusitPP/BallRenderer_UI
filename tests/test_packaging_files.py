
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_build_script_creates_ballrenderer_exe():
    text = (ROOT / "build_exe.bat").read_text(encoding="utf-8")
    assert "PyInstaller" in text
    assert "--onefile" in text
    assert "--windowed" in text
    assert "--name BallRenderer" in text


def test_requirements_include_runtime_and_builder():
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "numpy" in text
    assert "opencv-python" in text
    assert "pyinstaller" in text


def test_readme_mentions_ffmpeg_and_build():
    text = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    assert "ffmpeg" in text
    assert "build_exe.bat" in text
    assert "ballrenderer.exe" in text


def test_build_script_auto_finds_python():
    text = (ROOT / "build_exe.bat").read_text(encoding="utf-8").lower()
    assert ".venv\\scripts\\python.exe" in text
    assert "circle_line_battle_240fps" in text
    assert "py -3" in text
    assert "where python" in text
    assert "python was not found" in text
