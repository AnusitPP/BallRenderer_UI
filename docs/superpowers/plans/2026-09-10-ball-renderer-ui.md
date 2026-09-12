# Ball Renderer UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Build a Windows desktop UI around the existing renderer and package all source/build files in a ZIP.

**Architecture:** `app.py` launches `main.py` as a subprocess and translates UI controls into CLI flags. Progress output from the renderer is parsed and reflected in the UI without blocking the window.

**Tech Stack:** Python 3, Tkinter/ttk, OpenCV, NumPy, PyInstaller

**Spec:** `docs/superpowers/specs/2026-09-10-ball-renderer-ui-design.md`

## Global Constraints
- Windows-first launcher.
- Keep `main.py` usable from CMD.
- TikTok preset remains 1080x1920.
- UI must expose spike, physics, render, appearance, and audio controls.
- Rendering must run in a background subprocess.
- ZIP must include build instructions.

---

### Task 1: Renderer flags
**Files:** Modify `main.py`; Test `tests/test_main_flags.py`

- [x] Add CLI flags for rainbow border, random ball color, and audio enable/disable.
- [x] Verify generated command-line behavior using parser-level tests.
- [x] Keep existing defaults compatible.

### Task 2: Desktop launcher
**Files:** Create `app.py`; Test `tests/test_app_command.py`

- [x] Add configuration model and command builder.
- [x] Build CustomTkinter controls and TikTok preset.
- [x] Launch renderer in a subprocess and stream stdout.
- [x] Parse `Rendering [...] XX.XX%` progress into a progress bar.
- [x] Add Stop and Open Output Folder actions.

### Task 3: Packaging
**Files:** Create `requirements.txt`, `build_exe.bat`, `README.md`

- [x] Add runtime/build dependencies.
- [x] Build with PyInstaller using `--add-data main.py;.`.
- [x] Document FFmpeg PATH requirement and EXE build/run flow.

### Task 4: Verification and ZIP
**Files:** Test entire project and create ZIP.

- [x] Run syntax compilation for `app.py` and `main.py`.
- [x] Run unit tests.
- [x] Verify ZIP contents.
