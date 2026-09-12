# Ball Renderer UI v4 Design

## Goal
Provide a Windows desktop renderer that exposes the animation's main controls without requiring CMD edits, while keeping `main.py` usable directly.

## Features
- 1–8 active balls with ball/ball collision.
- Optional rotating spikes with configurable count.
- Hidden corner HUD by default.
- Rainbow rim and random ball color toggles.
- Gravity, speed growth, max speed, and ball growth controls.
- TikTok preset: 1080×1920.
- Bounce-note audio from built-in, JSON, or MIDI melody data.
- Instruments: piano, pluck, bell, synth.
- Volume, transpose, loop, and restart-on-break controls.
- External `melodies` directory next to the EXE. New files require only Refresh, not an EXE rebuild.
- Overall progress covers frame rendering, audio synthesis, and FFmpeg mux/encoding.

## Runtime architecture
`app.py` is both the GUI entrypoint and packaged child-process entrypoint. In source mode it re-launches itself through Python with `--renderer`; in packaged mode `BallRenderer.exe` re-launches itself with the same flag. The renderer stays outside the Tk event loop, so the GUI remains responsive.

`main.py` implements physics, drawing, melody loading, audio synthesis, FFmpeg discovery, GPU/CPU encoding fallback, and stage progress reporting.

## Melody files
JSON contains a MIDI note sequence and optional metadata. MIDI files are read through `mido`; when notes occur at the same timestamp, the highest note is used as the melody line.

## Packaging
`build_exe.bat` locates Python, creates a local `.venv`, installs dependencies, builds `BallRenderer.exe`, then copies the external `melodies` directory into `dist`.
