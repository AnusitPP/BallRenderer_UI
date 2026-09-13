import json
import math
import wave
import subprocess
from pathlib import Path
import numpy as np
import mido

def extract_midi_melody(path):
    midi = mido.MidiFile(str(path))
    absolute_tick = 0
    grouped = {}

    for msg in mido.merge_tracks(midi.tracks):
        absolute_tick += int(msg.time)
        if msg.type == "note_on" and getattr(msg, "velocity", 0) > 0:
            grouped.setdefault(absolute_tick, []).append(int(msg.note))

    return [max(grouped[tick]) for tick in sorted(grouped)]


def load_melody_file(path):
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        notes = [int(n) for n in data.get("notes", [])]
        if not notes:
            raise ValueError(f"No notes found in {path.name}")

        return {
            "name": str(data.get("name", path.stem)),
            "notes": notes,
            "instrument": str(data.get("instrument", "piano")).lower(),
            "volume": float(data.get("volume", 0.80)),
            "loop": bool(data.get("loop", True)),
            "restart_on_break": bool(data.get("restart_on_break", True)),
        }

    if suffix in (".mid", ".midi"):
        notes = extract_midi_melody(path)
        if not notes:
            raise ValueError(f"No note_on events found in {path.name}")

        return {
            "name": path.stem,
            "notes": notes,
            "instrument": "piano",
            "volume": 0.80,
            "loop": True,
            "restart_on_break": True,
        }

    raise ValueError("Melody file must be .json, .mid, or .midi")


