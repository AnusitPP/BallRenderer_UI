import json
import math
import wave
import subprocess
from pathlib import Path
import numpy as np
import mido

def midi_to_hz(note):
    return 440.0 * (2.0 ** ((float(note) - 69.0) / 12.0))


def synth_note(note, duration, sample_rate, instrument, volume):
    f = midi_to_hz(note)
    n = max(1, int(duration * sample_rate))
    x = np.arange(n, dtype=np.float64) / sample_rate

    attack = np.minimum(1.0, x / 0.006)

    if instrument == "pluck":
        env = attack * np.exp(-x * 13.0)
        sig = (
            0.76 * np.sin(2 * np.pi * f * x)
            + 0.16 * np.sin(2 * np.pi * f * 2.0 * x)
            + 0.08 * np.sin(2 * np.pi * f * 3.0 * x)
        )
    elif instrument == "bell":
        env = attack * np.exp(-x * 4.8)
        sig = (
            0.58 * np.sin(2 * np.pi * f * x)
            + 0.23 * np.sin(2 * np.pi * f * 2.01 * x)
            + 0.13 * np.sin(2 * np.pi * f * 3.98 * x)
            + 0.06 * np.sin(2 * np.pi * f * 6.05 * x)
        )
    elif instrument == "synth":
        env = attack * np.exp(-x * 6.5)
        sig = (
            0.55 * np.sin(2 * np.pi * f * x)
            + 0.30 * np.sin(2 * np.pi * f * 1.005 * x)
            + 0.15 * np.sin(2 * np.pi * f * 2.0 * x)
        )
    else:  # piano
        env = attack * np.exp(-x * 7.0)
        sig = (
            0.68 * np.sin(2 * np.pi * f * x)
            + 0.14 * np.sin(2 * np.pi * f * 2.0 * x)
            + 0.06 * np.sin(2 * np.pi * f * 3.0 * x)
            + 0.12 * np.sin(2 * np.pi * f * 1.003 * x)
        )

    return sig * env * float(volume)


def make_audio(events, seconds, sample_rate, out_wav, instrument="piano", note_volume=0.8):
    total = int(seconds * sample_rate)
    audio = np.zeros(total, dtype=np.float64)

    for event in events:
        t, kind, value = event
        start = int(float(t) * sample_rate)
        if start >= total:
            continue

        if kind == "note":
            sig = synth_note(
                int(value),
                0.26 if instrument == "bell" else 0.22,
                sample_rate,
                instrument,
                note_volume * 0.18,
            )
        elif kind == "spike":
            n = int(0.14 * sample_rate)
            x = np.arange(n, dtype=np.float64) / sample_rate
            env = np.exp(-x * 24.0)
            sig = (
                0.55 * np.sin(2 * np.pi * 120.0 * x)
                + 0.45 * np.sin(2 * np.pi * 70.0 * x)
            ) * env * 0.20
        else:
            n = int(0.06 * sample_rate)
            x = np.arange(n, dtype=np.float64) / sample_rate
            sig = np.sin(2 * np.pi * 660.0 * x) * np.exp(-x * 35.0) * 0.06

        n = min(len(sig), total - start)
        if n > 0:
            audio[start:start + n] += sig[:n]

    audio = np.clip(audio, -1.0, 1.0)
    pcm = (audio * 32767).astype(np.int16)

    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())


