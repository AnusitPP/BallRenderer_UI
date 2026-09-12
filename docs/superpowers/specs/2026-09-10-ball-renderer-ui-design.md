# Ball Renderer UI Design

## Goal
Wrap the existing Python renderer in a Windows desktop UI that can be packaged as a single EXE launcher.

## User flow
The user opens the launcher, adjusts rendering controls, starts a render, watches live progress/logs, and can open the output folder when finished.

## Controls
- Spikes enabled/disabled
- Spike count
- Gravity
- Speed growth
- Max speed
- Ball growth
- FPS
- Duration
- Width/height with TikTok 1080x1920 preset
- Rainbow border enabled/disabled
- Random ball color enabled/disabled
- Audio mode: Bounce Notes / Mute
- Output filename

## Architecture
- `app.py`: Tkinter/ttk GUI and subprocess orchestration.
- `main.py`: renderer CLI; receives all options from the UI and emits progress lines.
- `build_exe.bat`: installs dependencies and builds a Windows executable with PyInstaller.
- `requirements.txt`: runtime/build dependencies.
- `README.md`: Windows setup and build instructions.

The UI invokes `main.py` as a subprocess so rendering stays isolated from the GUI event loop. Stdout is streamed into the log box and parsed for percentage progress.

## Packaging
PyInstaller builds the UI executable. The packaged launcher locates the bundled `main.py` through PyInstaller's `_MEIPASS` extraction directory.

## Error handling
- Invalid numeric values are rejected before render.
- Duplicate render starts are blocked.
- Render failures show the subprocess exit code.
- The Stop button terminates the active render process.
- Open Output Folder works only after an output directory exists.
