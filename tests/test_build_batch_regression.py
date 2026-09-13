
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_build_batch_does_not_depend_on_goto_labels():
    text = (ROOT / "build_exe.bat").read_text(encoding="utf-8").lower()
    assert "goto :python_found" not in text
    assert ":python_found" not in text


def test_build_batch_invokes_detected_python_path_safely():
    text = (ROOT / "build_exe.bat").read_text(encoding="utf-8").lower()
    assert 'set "python_exe=' in text
    assert '"%python_exe%" %python_args% --version' in text


def test_build_batch_has_windows_crlf_line_endings():
    data = (ROOT / "build_exe.bat").read_bytes()
    assert b"\r\n" in data
    assert data.count(b"\r\n") > 20
