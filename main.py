from render.ffmpeg import hidden_process_kwargs, _append_video_encoder_options, build_original_audio_ffmpeg_cmd, find_ffmpeg, ffmpeg_has_nvenc_from_text, ffmpeg_has_nvenc, build_ffmpeg_cmd, report_progress, run_ffmpeg_with_progress
from audio.synthesizer import *
from audio.onset import *
from audio.mixer import *
import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
import wave
from dataclasses import dataclass
from pathlib import Path

import cv2
import mido
import numpy as np


from engines.circle.physics import *
from engines.circle.drawing import *
from engines.circle.drawing import _draw_ball_number
from core.config import build_arg_parser
from engines.circle.simulation import CircleSimulation








































def main(argv=None):
    args = build_arg_parser().parse_args(argv)

    final_out = Path(args.out).expanduser().resolve()
    final_out.parent.mkdir(parents=True, exist_ok=True)
    silent_video = final_out.with_suffix(".silent.mp4")
    audio_wav = final_out.with_suffix(".wav")
    source_temp_wav = final_out.with_suffix(".source.wav")

    ffmpeg = None
    source_samples = []
    if args.audio and args.audio_mode in ("original", "bounce-samples"):
        source_path = Path(args.audio_file).expanduser()
        if not args.audio_file:
            raise ValueError(
                f"--audio-file is required for audio mode: {args.audio_mode}"
            )
        if not source_path.exists():
            raise FileNotFoundError(f"Audio file not found: {source_path}")

        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            raise RuntimeError(
                "FFmpeg is required for Original MP3 / Bounce Samples audio mode."
            )

        if args.audio_mode == "bounce-samples":
            report_progress(0.0, "Analyzing source audio")
            source_samples = prepare_bounce_samples(
                ffmpeg,
                source_path,
                source_temp_wav,
                args.sample_rate,
                args.sample_ms,
            )
            if not source_samples:
                raise RuntimeError("Could not extract bounce samples from audio file.")
            print(
                f"Prepared {len(source_samples)} source-audio bounce samples.",
                flush=True,
            )

    engine = CircleSimulation(args, source_samples=source_samples)
    args = engine.config
    W, H, FPS = engine.W, engine.H, engine.FPS
    total_frames = engine.total_frames
    melody = engine.melody
    sound_events = engine.state.audio_events

    writer = cv2.VideoWriter(
        str(silent_video),
        cv2.VideoWriter_fourcc(*"mp4v"),
        FPS,
        (W, H),
    )
    if not writer.isOpened():
        raise RuntimeError("Cannot create video writer")

    render_started = time.perf_counter()
    report_progress(0.0, "Rendering frames")

    for frame in range(total_frames):
        engine.advance_frame()
        img = engine.draw_frame()

        writer.write(img)

        render_ratio = (frame + 1) / total_frames
        overall = render_ratio * 90.0
        elapsed = time.perf_counter() - render_started
        eta = elapsed * (1.0 - render_ratio) / render_ratio if render_ratio > 0 else 0.0

        if frame == total_frames - 1 or frame % max(1, FPS // 3) == 0:
            report_progress(overall, "Rendering frames")
            print(
                f"\rRendering {render_ratio * 100:6.2f}% "
                f"| {frame + 1}/{total_frames} "
                f"| Elapsed {int(elapsed // 60):02d}:{int(elapsed % 60):02d} "
                f"| ETA {int(eta // 60):02d}:{int(eta % 60):02d}",
                end="",
                flush=True,
            )

    writer.release()
    print()

    if not args.audio:
        report_progress(96.0, "Finalizing silent video")
        silent_video.replace(final_out)
        report_progress(100.0, "Complete")
    else:
        if args.audio_mode == "original":
            report_progress(92.0, "Preparing original audio")
            if ffmpeg is None:
                ffmpeg = find_ffmpeg()
            if not ffmpeg:
                raise RuntimeError("FFmpeg is required for Original MP3 / Audio mode.")

            source_audio = Path(args.audio_file).expanduser()
            use_nvenc = ffmpeg_has_nvenc(ffmpeg)
            cmd = build_original_audio_ffmpeg_cmd(
                ffmpeg,
                silent_video,
                source_audio,
                final_out,
                use_nvenc,
                source_volume=args.source_volume,
            )

            try:
                run_ffmpeg_with_progress(
                    cmd,
                    args.seconds,
                    progress_start=92.0,
                    progress_end=100.0,
                )
            except subprocess.CalledProcessError:
                if not use_nvenc:
                    raise

                print("NVENC failed. Retrying with CPU x264...", flush=True)
                report_progress(92.0, "Retrying with CPU x264")
                cmd = build_original_audio_ffmpeg_cmd(
                    ffmpeg,
                    silent_video,
                    source_audio,
                    final_out,
                    False,
                    source_volume=args.source_volume,
                )
                run_ffmpeg_with_progress(
                    cmd,
                    args.seconds,
                    progress_start=92.0,
                    progress_end=100.0,
                )

            silent_video.unlink(missing_ok=True)

        else:
            if args.audio_mode == "bounce-samples":
                report_progress(90.5, "Building bounce samples audio")
                make_bounce_sample_audio(
                    sound_events,
                    args.seconds,
                    args.sample_rate,
                    audio_wav,
                    source_samples,
                    source_volume=args.source_volume,
                )
            else:
                report_progress(90.5, "Creating note audio")
                make_audio(
                    sound_events,
                    args.seconds,
                    args.sample_rate,
                    audio_wav,
                    instrument=args.instrument,
                    note_volume=args.note_volume,
                )

            report_progress(92.0, "Preparing encoder")

            if ffmpeg is None:
                ffmpeg = find_ffmpeg()

            if not ffmpeg:
                silent_video.replace(final_out)
                audio_wav.unlink(missing_ok=True)
                print("WARNING: ffmpeg not found. Saved silent video only.")
                report_progress(100.0, "Complete (silent: FFmpeg missing)")
            else:
                use_nvenc = ffmpeg_has_nvenc(ffmpeg)
                cmd = build_ffmpeg_cmd(
                    ffmpeg,
                    silent_video,
                    audio_wav,
                    final_out,
                    use_nvenc,
                )

                try:
                    run_ffmpeg_with_progress(
                        cmd,
                        args.seconds,
                        progress_start=92.0,
                        progress_end=100.0,
                    )
                except subprocess.CalledProcessError:
                    if not use_nvenc:
                        raise

                    print("NVENC failed. Retrying with CPU x264...", flush=True)
                    report_progress(92.0, "Retrying with CPU x264")
                    cmd = build_ffmpeg_cmd(
                        ffmpeg,
                        silent_video,
                        audio_wav,
                        final_out,
                        False,
                    )
                    run_ffmpeg_with_progress(
                        cmd,
                        args.seconds,
                        progress_start=92.0,
                        progress_end=100.0,
                    )

                silent_video.unlink(missing_ok=True)
                audio_wav.unlink(missing_ok=True)

    print(f"Saved: {final_out}")
    print(f"Ball count: {args.ball_count}")
    print(f"Spike count: {args.spike_count}")
    print(f"Audio mode: {args.audio_mode}")
    if args.audio_mode == "synth":
        print(f"Melody: {melody['name']}")
        print(f"Instrument: {args.instrument}")
    elif args.audio_file:
        print(f"Source audio: {args.audio_file}")


if __name__ == "__main__":
    main()



