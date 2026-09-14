"""FFmpeg discovery, command building and progress shared by every engine."""
import os
import sys
import shutil
import subprocess
from pathlib import Path


def find_ffmpeg(search_root=None, *, bundled_root=None, configured_path=None):
    """Resolve environment, PATH, bundled executable, then configured location.

    search_root preserves the legacy explicit discovery API, without scanning a
    particular user's Downloads folder during normal application startup.
    """
    if search_root is not None:
        root = Path(search_root)
        candidates = [root / 'bin' / 'ffmpeg.exe', *sorted(root.glob('ffmpeg-*/bin/ffmpeg.exe'), reverse=True)]
        return next((str(p) for p in candidates if p.is_file()), shutil.which('ffmpeg'))
    use_default_locations = bundled_root is None
    base = Path(bundled_root) if bundled_root is not None else (
        Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
    )
    name = 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'
    candidates = [os.environ.get('FFMPEG_EXE', '').strip().strip('"'), shutil.which('ffmpeg'),
                  base / name, base / 'bin' / name]
    if getattr(sys, '_MEIPASS', None):
        candidates.extend([Path(sys._MEIPASS) / name, Path(sys._MEIPASS) / 'bin' / name])
    candidates.append(configured_path)
    user_profile = os.environ.get('USERPROFILE')
    if use_default_locations and user_profile and os.name == 'nt':
        downloads = Path(user_profile) / 'Downloads'
        candidates.extend(sorted(downloads.glob('ffmpeg-*/bin/ffmpeg.exe'), reverse=True))
        candidates.append(downloads / 'ffmpeg' / 'bin' / 'ffmpeg.exe')
    return next((str(Path(p).expanduser()) for p in candidates if p and Path(p).expanduser().is_file()), None)


def encode_video(ffmpeg_path, silent_video, audio_wav, final_out, duration_seconds):
    """Encode H.264, retry on CPU if an advertised NVENC device cannot run."""
    use_nvenc = ffmpeg_has_nvenc(ffmpeg_path)
    for hardware in ([True, False] if use_nvenc else [False]):
        if audio_wav:
            cmd = build_ffmpeg_cmd(ffmpeg_path, silent_video, audio_wav, final_out, hardware)
        else:
            cmd = [str(ffmpeg_path), '-y', '-i', str(silent_video)]
            _append_video_encoder_options(cmd, hardware)
            cmd += ['-pix_fmt', 'yuv420p', '-an', '-progress', 'pipe:1', '-nostats', str(final_out)]
        try:
            run_ffmpeg_with_progress(cmd, duration_seconds)
            return
        except subprocess.CalledProcessError:
            if not hardware:
                raise
            report_progress(92, 'NVENC failed; retrying CPU x264')

def hidden_process_kwargs():
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}

def _append_video_encoder_options(cmd, use_nvenc):
    if use_nvenc:
        cmd += [
            "-c:v", "h264_nvenc",
            "-preset", "p7",
            "-tune", "hq",
            "-rc", "vbr",
            "-cq", "15",
            "-b:v", "0",
        ]
    else:
        cmd += [
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "15",
        ]
    return cmd

def build_original_audio_ffmpeg_cmd(
    ffmpeg_path,
    silent_video,
    source_audio,
    final_out,
    use_nvenc,
    source_volume=1.0,
):
    cmd = [
        str(ffmpeg_path),
        "-y",
        "-i", str(silent_video),
        "-i", str(source_audio),
        "-map", "0:v:0",
        "-map", "1:a:0",
    ]
    _append_video_encoder_options(cmd, use_nvenc)

    if abs(float(source_volume) - 1.0) > 1e-6:
        cmd += ["-filter:a", f"volume={float(source_volume):.4f}"]

    cmd += [
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-progress", "pipe:1",
        "-nostats",
        str(final_out),
    ]
    return cmd

def ffmpeg_has_nvenc_from_text(text):
    return "h264_nvenc" in text

def ffmpeg_has_nvenc(ffmpeg_path):
    try:
        result = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            **hidden_process_kwargs(),
        )
        combined = (result.stdout or "") + "\n" + (result.stderr or "")
        return ffmpeg_has_nvenc_from_text(combined)
    except Exception:
        return False

def build_ffmpeg_cmd(ffmpeg_path, silent_video, audio_wav, final_out, use_nvenc):
    cmd = [
        ffmpeg_path,
        "-y",
        "-i", str(silent_video),
        "-i", str(audio_wav),
    ]

    _append_video_encoder_options(cmd, use_nvenc)

    cmd += [
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "160k",
        "-shortest",
        "-progress", "pipe:1",
        "-nostats",
        str(final_out),
    ]
    return cmd

def report_progress(value, stage):
    value = max(0.0, min(100.0, float(value)))
    print(f"APP_PROGRESS {value:.2f} {stage}", flush=True)

def run_ffmpeg_with_progress(cmd, duration_seconds, progress_start=92.0, progress_end=100.0):
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        universal_newlines=True,
        **hidden_process_kwargs(),
    )

    last = progress_start
    report_progress(last, "Muxing audio/video")

    for raw in proc.stdout:
        line = raw.strip()
        seconds = None

        if line.startswith("out_time_us="):
            try:
                seconds = int(line.split("=", 1)[1]) / 1_000_000.0
            except ValueError:
                pass
        elif line.startswith("out_time_ms="):
            try:
                seconds = int(line.split("=", 1)[1]) / 1_000_000.0
            except ValueError:
                pass

        if seconds is not None and duration_seconds > 0:
            ratio = max(0.0, min(1.0, seconds / duration_seconds))
            value = progress_start + ratio * (progress_end - progress_start)
            if value >= last:
                last = value
                report_progress(value, "Muxing audio/video")

    code = proc.wait()
    if code != 0:
        raise subprocess.CalledProcessError(code, cmd)

    report_progress(progress_end, "Complete")
