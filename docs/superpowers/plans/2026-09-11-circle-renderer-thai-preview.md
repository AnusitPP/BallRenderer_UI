# Circle Renderer Thai Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the circular renderer and add a Thai slider-based UI with static preview and a fixed, visible start-render button.

**Architecture:** Reuse the existing v8 circular physics/audio engine in `main.py`, add only the renderer parameters needed by the new UI, and replace the existing Tkinter UI with a Thai two-column control/preview layout. The render child process stays separate from the GUI. Static preview reuses the renderer's circle/spike drawing helpers.

**Tech Stack:** Python 3, Tkinter, NumPy, OpenCV, mido, FFmpeg, PyInstaller, pytest

**Spec:** `docs/superpowers/specs/2026-09-11-circle-renderer-thai-preview-design.md`

## Global Constraints
- Renderer source filename stays `main.py`.
- Default output is 1080x1920 at 240 FPS.
- Audio is synth/MIDI/JSON bounce notes only.
- No original MP3 or bounce-sample mode in the new UI.
- Primary render button is fixed and always visible.
- Package is a complete ZIP install.

---

### Task 1: Renderer parameters for UI control

**Files:**
- Modify: `main.py`
- Test: `tests/test_v11_circle_renderer.py`

**Interfaces:**
- Consumes: existing circular renderer physics and draw helpers.
- Produces: `--initial-angle`, `--initial-speed`, `--arena-scale` CLI arguments and compatible spawn behavior.

- [ ] Write failing tests asserting the parser exposes the three new flags and `spawn_ball` can receive a fixed initial angle/speed.
- [ ] Run the focused test and verify it fails.
- [ ] Add minimal parser flags and spawn parameters.
- [ ] Use `arena_scale` when computing arena radius.
- [ ] Run the focused test and verify it passes.

### Task 2: Simplify audio to bounce-note mode

**Files:**
- Modify: `main.py`
- Test: `tests/test_v11_circle_renderer.py`

**Interfaces:**
- Consumes: existing MIDI/JSON loading and `make_audio`.
- Produces: synth-only runtime path with MIDI/JSON note sequences.

- [ ] Write a failing test that the new UI command does not emit `--audio-mode` or `--audio-file`.
- [ ] Run the test and verify it fails.
- [ ] Keep synth note-event generation in renderer and remove real-audio command usage from the UI path.
- [ ] Run the test and verify it passes.

### Task 3: Thai UI with static preview and fixed start button

**Files:**
- Replace: `app.py`
- Test: `tests/test_v11_circle_renderer.py`

**Interfaces:**
- Consumes: renderer CLI flags and renderer drawing helpers.
- Produces: `build_renderer_args(config)`, static preview generation, fixed bottom action bar.

- [ ] Write failing tests for circle arguments, Thai start button text, and absence of maze arguments.
- [ ] Run tests and verify they fail.
- [ ] Implement Thai control panel and preview panel.
- [ ] Implement slider controls for circle settings.
- [ ] Implement static preview using circle/spike/ball drawing helpers.
- [ ] Add fixed green `▶ เริ่มเรนเดอร์` button outside the scrollable panel.
- [ ] Run tests and verify they pass.

### Task 4: Documentation and packaging

**Files:**
- Modify: `README.md`
- Modify: `HOW_TO_INSTALL_TH.txt`
- Modify: `VERSION.txt`
- Modify: `build_exe.bat`
- Verify: complete ZIP contents

**Interfaces:**
- Consumes: final source tree.
- Produces: install-ready ZIP.

- [ ] Update Thai installation/use documentation.
- [ ] Update version to v11 circle preview.
- [ ] Run Python syntax compilation.
- [ ] Run full pytest suite.
- [ ] Run a short low-resolution silent render smoke test.
- [ ] Package the full folder into `CircleBallRenderer_v11_THAI_PREVIEW_COMPLETE.zip`.
