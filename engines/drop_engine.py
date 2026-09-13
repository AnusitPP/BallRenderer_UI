"""CLI renderer for Ball Drop Shatter mode."""
import argparse
import tempfile
from pathlib import Path
import cv2

from audio.merge import _decode_audio_mono, _mix_audio_timeline
from engines.drop.simulation import DropSimulation
from render.ffmpeg import encode_video, find_ffmpeg, report_progress


def cli(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default='output/drop_shatter_final.mp4')
    parser.add_argument('--width', type=int, default=1080)
    parser.add_argument('--height', type=int, default=1920)
    parser.add_argument('--fps', type=int, default=60)
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--seed', type=int, default=11)
    parser.add_argument('--spawn-interval', type=float, default=1.2)
    parser.add_argument('--one-shot', type=int, choices=(0, 1), default=1)
    parser.add_argument('--size-script', default='')
    parser.add_argument('--segment-seconds', type=float, default=5.0)
    parser.add_argument('--auto-foam-from-size', type=int, choices=(0, 1), default=0)
    parser.add_argument('--gravity', type=float, default=500)
    parser.add_argument('--initial-speed', type=float, default=0)
    parser.add_argument('--ball-size', type=float, default=64)
    parser.add_argument('--ball-color', default='#ff4d4d')
    parser.add_argument('--foam-color', default='#ffffff')
    parser.add_argument('--ball-image', default='')
    parser.add_argument('--foam-image', default='')
    parser.add_argument('--particle-count', type=int, default=300)
    parser.add_argument('--particle-budget', type=int, default=600)
    parser.add_argument('--particle-size', type=float, default=8)
    parser.add_argument('--particle-life', type=float, default=6.0)
    parser.add_argument('--remove-foam-on-floor', type=int, choices=(0, 1), default=0)
    parser.add_argument('--particle-speed', type=float, default=500)
    parser.add_argument('--spike-count', type=int, default=12)
    parser.add_argument('--spike-height', type=float, default=85)
    parser.add_argument('--shatter-sound-file', default='')
    parser.add_argument('--floor-sound-file', default='')
    parser.add_argument('--floor-sound-chance', type=float, default=.5)
    parser.add_argument('--sound-volume', type=float, default=.9)
    return parser.parse_args(argv)


def render(args):
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError('FFmpeg not found')
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='drop_', dir=output.parent))
    silent = temp / 'silent.mp4'
    audio_path = temp / 'audio.wav'
    sim = DropSimulation(args)
    writer = cv2.VideoWriter(str(silent), cv2.VideoWriter_fourcc(*'mp4v'), args.fps, (args.width, args.height))
    if not writer.isOpened():
        raise RuntimeError('Could not open Drop video writer')
    frames = max(1, int(args.seconds * args.fps))
    success = False
    try:
        for frame in range(frames):
            sim.advance_frame()
            writer.write(sim.draw_frame())
            if frame % max(1, frames // 100) == 0:
                report_progress(90 * (frame + 1) / frames, 'Ball Drop Shatter')
        writer.release()
        clip = _decode_audio_mono(args.shatter_sound_file, ffmpeg)
        floor_clip = _decode_audio_mono(args.floor_sound_file, ffmpeg)
        _mix_audio_timeline(audio_path, sim.audio_events, args.seconds, args.sound_volume, clip, floor_clip)
        encode_video(ffmpeg, silent, audio_path, output, args.seconds)
        success = True
        report_progress(100, 'Complete')
    finally:
        writer.release()
        if success:
            silent.unlink(missing_ok=True)
            audio_path.unlink(missing_ok=True)
            temp.rmdir()


def main(argv=None):
    render(cli(argv))


if __name__ == '__main__':
    main()
