# Ball Renderer UI v4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the Windows Ball Renderer with multi-ball rendering, hidden HUD, full mux progress, and an external melody manager.

**Architecture:** The GUI launches the renderer as a child process and parses `APP_PROGRESS` lines. Melody files remain external to the EXE so new JSON/MIDI files can be added without rebuilding.

**Tech Stack:** Python 3, Tkinter/ttk, OpenCV, NumPy, Mido, FFmpeg, PyInstaller

**Spec:** `docs/superpowers/specs/2026-09-10-ball-renderer-ui-v4-design.md`

## Global Constraints
- Windows-first.
- 1080×1920 TikTok preset.
- `main.py` remains CLI-compatible.
- 1–8 balls.
- HUD off by default.
- JSON/MIDI melody import.
- External melody folder survives independently of the EXE.
- Progress reaches 100% only after final mux/encode completes.

---

### Task 1: Renderer controls
- [x] Add multi-ball state and ball/ball collisions.
- [x] Add HUD, appearance, and audio CLI flags.
- [x] Keep rotating spikes configurable.

### Task 2: Melody engine
- [x] Add JSON melody loader.
- [x] Add MIDI melody extraction.
- [x] Add piano, pluck, bell, and synth voices.
- [x] Add transpose, volume, looping, and restart-on-break behavior.

### Task 3: Full progress
- [x] Map frame rendering to 0–90%.
- [x] Report audio preparation at 90–92%.
- [x] Parse FFmpeg progress into 92–100%.
- [x] Preserve NVENC-to-x264 fallback.

### Task 4: Desktop UI
- [x] Add Ball Count.
- [x] Add HUD toggle.
- [x] Add Melody tab and import actions.
- [x] Add full stage/progress display.
- [x] Add output and melody folder actions.

### Task 5: Windows packaging
- [x] Add Mido dependency.
- [x] Build a local `.venv`.
- [x] Build one-file `BallRenderer.exe`.
- [x] Copy external melodies to `dist\melodies`.
- [x] Add START_HERE installer/build launcher.

### Task 6: Verification
- [x] Run unit/regression tests.
- [x] Run source-mode child-process smoke render with 3 balls and audio.
- [x] Build clean ZIP.
