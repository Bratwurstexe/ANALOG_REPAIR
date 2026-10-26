# Development status

## Ready (0.1.0)

- **Desktop app (.NET 8 / Avalonia)** with a four-step workflow: Import, Trim, Repair and Export.
  - Import: drag and drop, whole folders, files given on the command line.
  - Trim: timeline editor with split, remove, bookmarks, zoom, undo and redo, waveform and real playback.
  - Repair: source choice *Tape* or *Film*, sliders for every stage, date stamp removal with a *Show* check, output size, speed, presets, optional look, and a frame preview with a split comparison.
  - Export: five file formats, live remaining time and cancel, joined clips, result player with a gain and headroom estimate and *Auto refine*.
- **Tape and film stages** (`movie.py`): deinterlacing, tape noise (tracking bands, head switch, line jitter), flicker, dust and scratches, stabilising and colour bleed. Each stage is off at 0 and compares with the nearest frame that really differs, so duplicated frames of a transfer do not hide dust or flicker.
- **Colour** (`analog.py`, `movie.py`): chroma re-estimated from six motion-aligned neighbours, then pulled back onto the brightness edges. Black-and-white footage passes untouched.
- **Date stamp** (`osd.py`): found by gradient coherence across the cut and refilled per region from the best-fitting neighbour; inpainting as the fallback.
- **Fusion and upscaling** (`upscale.py`, `gpu.py`): five-frame median fusion, 1.5× and 2×, *Keep film grain*, OpenCL on any GPU that passes a self-test.
- **Launcher** for Windows, macOS and Linux that installs and updates the app from the newest GitHub release.
- **Build workflow** that tests the engine, freezes it with PyInstaller and packages app, engine and FFmpeg for Windows, Linux (folder and AppImage) and macOS (Apple Silicon and Intel); a `v*` tag publishes a release with checksums.
- Automated engine tests: stages of the tape and film chain, date stamp, colour, look, formats, segments, export recovery, parallel pipeline, side bars, GPU against CPU (skipped without an OpenCL GPU).

## Decided

- **Name:** Analog Repair. Package `analogrepair`, engine `analogrepair-engine`, app `AnalogRepair.Desktop`, launcher `AnalogRepair.Launcher`, release assets `Analog-Repair-<tag>-…`. These names are what the launcher looks for and do not change.
- **No code signing.** Windows SmartScreen and macOS Gatekeeper warn on first start; the release notes explain how to open the app anyway.
- **Footage in docs/media:** public-domain or freely licensed clips, credited in `docs/media/CREDITS.md`, chosen from scenes without people.

## Open

1. **Colourising black-and-white film** from a few colour hints per scene. The stage has its place in the chain (`restoration._movie_stages`, after every repair and before fusion).
2. **Speed on long tapes.** No benchmark has been published yet; with every stage on, expect a few minutes of processing per minute of SD footage.
3. **Testing on Linux and macOS, and on AMD, Intel and Apple GPUs.** The builds are configured; the first release will be the first run of the packages there.
4. **App screenshots** for the README, once the first release is built.
