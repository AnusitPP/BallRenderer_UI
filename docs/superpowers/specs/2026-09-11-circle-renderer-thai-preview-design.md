# Circle Renderer Thai Preview Design

## Goal
Restore the pre-maze circular physics renderer and keep the new Thai customization UI, with a static image preview and an always-visible start-render button.

## Gameplay
- Circular arena centered in portrait video.
- Ball starts inside the circle and bounces with gravity, restitution, drag, speed growth, and ball growth.
- Rotating spikes remain available and can be enabled/disabled and counted.
- Oversized balls and spike hits use the existing explosion/respawn behavior.
- Multiple balls remain supported.
- Circular rainbow border remains supported.

## Customization UI
- Entire interface is Thai-first.
- Main controls use sliders for:
  - initial angle
  - gravity
  - initial speed
  - speed growth
  - maximum speed
  - base ball radius
  - ball growth per bounce
  - arena size
  - spike count
  - spike rotation speed
  - spike depth
  - trail is not required in this circle restoration
- Static preview image appears on the right.
- Preview updates after slider changes and has a manual refresh button.
- Bottom action bar is fixed and always visible.
- Primary action is a large green `▶ เริ่มเรนเดอร์` button.
- Secondary actions: stop render, update preview, open output folder.

## Audio
- Remove original MP3 soundtrack and bounce-sample modes from the UI and render command.
- Keep synthesized bounce-note audio only.
- Keep MIDI / JSON melody import and selectable instrument.
- One wall bounce advances to the next note.

## Render
- Default 1080x1920, 240 FPS.
- Existing FFmpeg/NVENC final mux flow remains.
- main.py remains the renderer source filename.

## Packaging
- Complete install ZIP, not a patch.
- Include START_HERE.bat, build_exe.bat, run_ui.bat, requirements.txt, README.md, HOW_TO_INSTALL_TH.txt, melodies/, tests/.
