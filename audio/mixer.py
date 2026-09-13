import json
import math
import wave
import subprocess
from pathlib import Path
import numpy as np
import mido
from audio.onset import *

def mix_bounce_sample_events(
    events,
    seconds,
    sample_rate,
    source_samples,
    volume=0.85,
):
    total = max(1, int(round(float(seconds) * int(sample_rate))))
    output = np.zeros(total, dtype=np.float32)

    if not source_samples:
        return output

    for t, kind, value in events:
        if kind != "sample":
            continue

        start = int(round(float(t) * sample_rate))
        if start >= total:
            continue

        sample = source_samples[int(value) % len(source_samples)]
        n = min(len(sample), total - start)
        if n > 0:
            output[start:start + n] += sample[:n] * float(volume)

    return output


def write_float_audio_wav(audio, sample_rate, out_wav):
    audio = np.asarray(audio, dtype=np.float32)
    audio = np.clip(audio, -1.0, 1.0)
    pcm = (audio * 32767.0).astype(np.int16)

    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(pcm.tobytes())


def make_bounce_sample_audio(
    events,
    seconds,
    sample_rate,
    out_wav,
    source_samples,
    source_volume=0.85,
):
    audio = mix_bounce_sample_events(
        events,
        seconds,
        sample_rate,
        source_samples,
        volume=source_volume,
    )

    # Keep the existing synthesized crash cue for spike / oversize explosions.
    for t, kind, _value in events:
        if kind != "spike":
            continue

        start = int(float(t) * sample_rate)
        if start >= len(audio):
            continue

        n = int(0.14 * sample_rate)
        x = np.arange(n, dtype=np.float64) / sample_rate
        env = np.exp(-x * 24.0)
        sig = (
            0.55 * np.sin(2 * np.pi * 120.0 * x)
            + 0.45 * np.sin(2 * np.pi * 70.0 * x)
        ) * env * 0.16
        count = min(len(sig), len(audio) - start)
        if count > 0:
            audio[start:start + count] += sig[:count].astype(np.float32)

    write_float_audio_wav(audio, sample_rate, out_wav)


