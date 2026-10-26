> [!IMPORTANT]
> **Want to stay up to date? Download the launcher.** It always installs the newest Analog Repair: pick your system, and it downloads the latest release, checks it, deletes the old version and starts the app.
> **[⬇ Windows](https://github.com/Bratwurstexe/ANALOG_REPAIR/releases/latest/download/Analog-Repair-Launcher-windows-x64.exe)** · **[macOS Apple Silicon](https://github.com/Bratwurstexe/ANALOG_REPAIR/releases/latest/download/Analog-Repair-Launcher-macos-apple-silicon.zip)** · **[macOS Intel](https://github.com/Bratwurstexe/ANALOG_REPAIR/releases/latest/download/Analog-Repair-Launcher-macos-intel.zip)** · **[Linux](https://github.com/Bratwurstexe/ANALOG_REPAIR/releases/latest/download/Analog-Repair-Launcher-linux-x64.tar.gz)**

Repair digitised tapes and film on your own computer: VHS, S-VHS, Hi8, Video8 and camcorder tapes, and 8 mm, Super 8 or 16 mm film. Unpack and start; the app, the video engine and FFmpeg are included, so you don't need to install Python or FFmpeg.

## Download

| Your system | File | Start |
|---|---|---|
| **Windows** 10 / 11 (64-bit) | `Analog-Repair-…-windows-x64.zip` | `AnalogRepair.Desktop.exe` |
| **macOS**, Apple Silicon (M1 and newer) | `Analog-Repair-…-macos-apple-silicon.zip` | `Analog Repair.app` |
| **macOS**, Intel | `Analog-Repair-…-macos-intel.zip` | `Analog Repair.app` |
| **Linux** (x64) | `Analog-Repair-…-linux-x64.AppImage` | `chmod +x` it, then start it |
| **Linux** (x64), plain folder | `Analog-Repair-…-linux-x64.tar.gz` | `./AnalogRepair.Desktop` |
| **Launcher** (recommended), Windows | `Analog-Repair-Launcher-windows-x64.exe` | double-click it |
| **Launcher**, macOS | `Analog-Repair-Launcher-macos-….zip` | `Analog Repair Launcher.app` |
| **Launcher**, Linux | `Analog-Repair-Launcher-linux-x64.tar.gz` | `./Analog-Repair-Launcher` |
| **Source code** | *Source code (zip)* or *(tar.gz)* below | see the README |

`SHA256SUMS.txt` lists the checksum of every package.

## New in 0.2.0

- **A simpler Repair page that fits on one screen:** start from a preset card (*VHS tape*, *Worn VHS tape*, *Camcorder tape*, *8 mm / Super 8*, *16 mm film*, *Archive, 2× Best*), pick the output size and speed, and find every slider, the source and the date stamp under *Advanced*, folded away by default. Changed values show as *Custom · based on …*; *Save as preset…* keeps them under your own name, and your presets can be renamed, updated or deleted. Presets saved with 0.1.0 appear as your own. Slimmer sliders throughout the app.

## 0.1.0: the first release

**Tape or film**
- Choose *Tape* (VHS, Hi8, camcorder) or *Film* (8 mm, Super 8, 16 mm) on the Repair page; each starts from settings made for it, and every repair has its own slider. 0 turns a repair off.
- **Tape noise:** rows torn by tracking noise are rebuilt from the frames around them, the torn band at the bottom of the picture is masked, and wobbling lines are put back in place.
- **Dust and scratches:** specks, dirt, tape dropouts and thin vertical scratches are refilled from the neighbouring frames.
- **Flicker** is evened out, **gate weave and shake** are steadied; slow exposure changes, pans and zooms stay.
- **Colour:** colour noise is re-estimated from the frames around, and the colour smear of tape is pulled back onto the edges. Black-and-white footage is left alone.
- **Remove date stamp:** a burned-in camcorder date and time is found and painted out; *Show* marks it first.
- Interlaced transfers are turned into full frames before anything else.

**Noise, size and look**
- Five-frame noise reduction; *Keep film grain* leaves some grain in.
- Multi-frame upscaling 1.5× or 2×.
- An optional finishing look: colour grade, glow, vignette, film grain and lens fringe, with the presets *Clean*, *Cinematic*, *Punchy* and *Retro*.

**Workflow**
- Timeline trim editor with split, remove, bookmarks, undo and redo, waveform and real playback.
- Frame preview with a split line, result player with original and repaired clip side by side, a gain and headroom estimate and *Auto refine*.
- Five file formats (MP4 H.264, MP4 H.265, MOV ProRes 422, MKV, WebM), batch export with live remaining time, joined clips, presets, and settings that are remembered.
- Uses the CPU and the GPU (NVIDIA, AMD, Intel or Apple) together.

**What it cannot do (yet)**
- It repairs what neighbouring frames can replace. Dirt that stays for several frames, a wandering scratch and a head-switch band torn in every frame stay visible or are only reduced.
- Colourising black-and-white film is planned for a later release.

## First start

- **Windows:** SmartScreen may warn about an unknown publisher. Choose *More info → Run anyway*.
- **macOS:** the app is not notarised. Right-click it and choose *Open*, or run `xattr -cr "Analog Repair.app"` in Terminal.
- **Linux:** if the file manager does not start it, run `chmod +x AnalogRepair.Desktop` once.

All processing stays on your computer. The application code is MIT licensed. The bundled components keep their own licences: Avalonia (MIT), NumPy (BSD), OpenCV (Apache-2.0) and FFmpeg (GPL, a separate program in the `ffmpeg` folder; source at https://ffmpeg.org/download.html). See `THIRD-PARTY-NOTICES.md` and `ffmpeg/FFMPEG-LICENSE.txt` in the package.
