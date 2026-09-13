import argparse
from engines.circle.physics import DEFAULT_BALL_COLORS

def build_arg_parser():
    ap = argparse.ArgumentParser()

    ap.add_argument("--out", default="tiktok_final.mp4")
    ap.add_argument("--fps", type=int, default=240)
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int, default=1920)
    ap.add_argument("--substeps", type=int, default=6)

    ap.add_argument("--initial-angle", type=float, default=35.0)
    ap.add_argument("--initial-speed", type=float, default=600.0)
    ap.add_argument("--arena-scale", type=float, default=1.0)
    ap.add_argument("--gap-enabled", type=int, choices=(0, 1), default=0)
    ap.add_argument("--gap-size", type=float, default=45.0)
    ap.add_argument("--gap-position", type=float, default=-90.0)

    ap.add_argument("--gravity", type=float, default=900.0)
    ap.add_argument("--wall-restitution", type=float, default=0.985)
    ap.add_argument("--bounce-growth", type=float, default=0.0)
    ap.add_argument("--wall-friction", type=float, default=0.0006)
    ap.add_argument("--air-drag", type=float, default=0.00018)
    ap.add_argument("--max-speed", type=float, default=1750.0)
    ap.add_argument("--speed-growth", type=float, default=1.004)

    ap.add_argument("--ball-count", type=int, default=1)
    ap.add_argument("--ball-lives", default="10")
    ap.add_argument("--pattern-file", default="")
    ap.add_argument(
        "--ball-color-mode",
        choices=("random", "same", "per-ball"),
        default=None,
    )
    ap.add_argument(
        "--ball-colors",
        default=",".join(DEFAULT_BALL_COLORS),
    )
    ap.add_argument("--base-radius", type=float, default=24.0)
    ap.add_argument("--growth", type=float, default=5.0)
    ap.add_argument("--max-ball-radius", type=float, default=None, help=argparse.SUPPRESS)
    ap.add_argument("--smooth-growth-speed", type=float, default=24.0)
    ap.add_argument("--motion-trail", type=int, choices=(0, 1), default=0)
    ap.add_argument("--trail-rainbow-speed", type=float, default=0.11)
    ap.add_argument("--trail-stamp-spacing", type=float, default=0.16)

    ap.add_argument("--spike-count", type=int, default=3)
    ap.add_argument("--rotation-speed", type=float, default=0.85)
    ap.add_argument("--spike-depth", type=float, default=34.0)
    ap.add_argument("--spike-width", type=float, default=15.0)
    ap.add_argument("--respawn-delay", type=float, default=0.12)
    ap.add_argument("--spike-duplicate", type=int, choices=(0, 1), default=0)
    ap.add_argument("--escape-duplicate", type=int, choices=(0, 1), default=0)
    ap.add_argument("--escape-hud", type=int, choices=(0, 1), default=0)
    ap.add_argument("--escape-countdown", type=int, choices=(0, 1), default=0)
    ap.add_argument("--escape-hud-x", type=float, default=50.0)
    ap.add_argument("--escape-hud-y", type=float, default=50.0)

    ap.add_argument("--rainbow-speed", type=float, default=0.12)
    ap.add_argument("--rainbow-border", type=int, choices=(0, 1), default=1)
    ap.add_argument("--random-ball-color", type=int, choices=(0, 1), default=1)
    ap.add_argument("--show-hud", type=int, choices=(0, 1), default=0)
    ap.add_argument("--show-ball-numbers", type=int, choices=(0, 1), default=1)
    ap.add_argument("--ball-number-color", default="#ffffff")

    ap.add_argument("--audio", type=int, choices=(0, 1), default=1)
    ap.add_argument(
        "--audio-mode",
        choices=("synth", "original", "bounce-samples"),
        default="synth",
    )
    ap.add_argument("--audio-file", default="")
    ap.add_argument("--source-volume", type=float, default=0.85)
    ap.add_argument("--sample-ms", type=int, default=240)
    ap.add_argument("--melody-file", default="")
    ap.add_argument("--instrument", choices=("piano", "pluck", "bell", "synth"), default="piano")
    ap.add_argument("--note-volume", type=float, default=0.80)
    ap.add_argument("--transpose", type=int, default=0)
    ap.add_argument("--melody-loop", type=int, choices=(0, 1), default=1)
    ap.add_argument("--restart-melody-on-break", type=int, choices=(0, 1), default=1)
    ap.add_argument("--sample-rate", type=int, default=48000)

    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--ball-images", default="")
    return ap


