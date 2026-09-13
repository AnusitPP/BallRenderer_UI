
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("renderer_main", ROOT / "main.py")
renderer_main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer_main)


def test_build_arg_parser_has_ui_flags():
    parser = renderer_main.build_arg_parser()
    args = parser.parse_args([
        "--rainbow-border", "0",
        "--random-ball-color", "0",
        "--audio", "0",
        "--spike-count", "4",
    ])
    assert args.rainbow_border == 0
    assert args.random_ball_color == 0
    assert args.audio == 0
    assert args.spike_count == 4
