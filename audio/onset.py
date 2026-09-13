import json
import math
import wave
import subprocess
from pathlib import Path
import numpy as np
import mido
from render.ffmpeg import hidden_process_kwargs

def read_wav_mono(path):
    """Read 16-bit PCM WAV as mono float32 in [-1, 1]."""
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        sample_rate = wf.getframerate()
        frame_count = wf.getnframes()
        raw = wf.readframes(frame_count)

    if sample_width != 2:
        raise ValueError("Decoded source WAV must be 16-bit PCM")

    pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    if channels > 1:
        pcm = pcm.reshape(-1, channels).mean(axis=1)

    return pcm / 32768.0, int(sample_rate)


def detect_audio_onsets(audio, sample_rate, min_gap_seconds=0.09):
    """
    Lightweight onset detector for extracting sequential song snippets.
    Uses short-time RMS rises, so it needs no extra audio-analysis package.
    """
    x = np.asarray(audio, dtype=np.float32).reshape(-1)
    if x.size == 0:
        return []

    sr = max(1, int(sample_rate))
    frame = max(8, int(sr * 0.020))
    hop = max(1, int(sr * 0.005))

    # Efficient moving RMS using cumulative sums.
    sq = x.astype(np.float64) ** 2
    csum = np.concatenate(([0.0], np.cumsum(sq)))
    starts = np.arange(0, max(1, x.size - frame + 1), hop, dtype=np.int64)
    ends = np.minimum(starts + frame, x.size)
    lengths = np.maximum(1, ends - starts)
    energy = (csum[ends] - csum[starts]) / lengths
    rms = np.sqrt(np.maximum(energy, 0.0))

    if rms.size < 3:
        return [0]

    novelty = np.maximum(0.0, np.diff(rms, prepend=rms[0]))
    positive = novelty[novelty > 0]

    if positive.size == 0:
        return [0]

    median = float(np.median(positive))
    mad = float(np.median(np.abs(positive - median))) + 1e-12
    percentile = float(np.percentile(positive, 70))
    threshold = max(median + 0.6 * mad, percentile * 0.75)
    threshold = min(threshold, float(np.max(positive)) * 0.85)

    candidates = []
    for i in range(1, novelty.size - 1):
        if (
            novelty[i] >= threshold
            and novelty[i] >= novelty[i - 1]
            and novelty[i] >= novelty[i + 1]
        ):
            candidates.append((i, float(novelty[i])))

    if not candidates:
        strongest = int(np.argmax(novelty))
        return [int(starts[min(strongest, len(starts) - 1)])]

    min_gap_frames = max(1, int(round(min_gap_seconds * sr / hop)))
    selected = []
    group = []

    for item in candidates:
        if not group or item[0] - group[-1][0] <= min_gap_frames:
            group.append(item)
        else:
            selected.append(max(group, key=lambda pair: pair[1]))
            group = [item]

    if group:
        selected.append(max(group, key=lambda pair: pair[1]))

    positions = [
        int(starts[min(index, len(starts) - 1)])
        for index, _strength in selected
    ]

    # Avoid a useless leading near-silence trigger unless it is the only one.
    if len(positions) > 1 and positions[0] < int(sr * 0.03):
        positions = positions[1:]

    return positions or [0]


def extract_bounce_samples(audio, sample_rate, onset_positions, sample_ms=240):
    """Extract fixed-length, softly faded snippets from detected attacks."""
    x = np.asarray(audio, dtype=np.float32).reshape(-1)
    sr = max(1, int(sample_rate))
    sample_len = max(16, int(round(sr * max(40, int(sample_ms)) / 1000.0)))
    pre_roll = int(round(sr * 0.012))
    fade_len = min(sample_len // 4, max(1, int(round(sr * 0.012))))

    result = []
    for onset in onset_positions:
        start = max(0, int(onset) - pre_roll)
        chunk = np.zeros(sample_len, dtype=np.float32)
        available = min(sample_len, max(0, x.size - start))
        if available > 0:
            chunk[:available] = x[start:start + available]

        if fade_len > 0:
            fade_in = np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
            fade_out = np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
            chunk[:fade_len] *= fade_in
            chunk[-fade_len:] *= fade_out

        peak = float(np.max(np.abs(chunk))) if chunk.size else 0.0
        if peak > 1.0:
            chunk /= peak

        result.append(chunk)

    return result


def decode_audio_to_wav(ffmpeg_path, source_path, out_wav, sample_rate):
    cmd = [
        str(ffmpeg_path),
        "-y",
        "-hide_banner",
        "-loglevel", "error",
        "-i", str(source_path),
        "-vn",
        "-ac", "1",
        "-ar", str(int(sample_rate)),
        "-c:a", "pcm_s16le",
        str(out_wav),
    ]
    subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **hidden_process_kwargs(),
    )


def prepare_bounce_samples(
    ffmpeg_path,
    source_path,
    temp_wav,
    sample_rate,
    sample_ms,
):
    decode_audio_to_wav(
        ffmpeg_path,
        source_path,
        temp_wav,
        sample_rate,
    )
    try:
        audio, decoded_sr = read_wav_mono(temp_wav)
        onsets = detect_audio_onsets(
            audio,
            decoded_sr,
            min_gap_seconds=max(0.055, min(0.14, sample_ms / 1000.0 * 0.40)),
        )
        samples = extract_bounce_samples(
            audio,
            decoded_sr,
            onsets,
            sample_ms=sample_ms,
        )
        return samples
    finally:
        Path(temp_wav).unlink(missing_ok=True)


