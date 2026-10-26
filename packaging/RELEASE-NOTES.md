> [!IMPORTANT]
> **Recommended: the launcher.** It always installs the newest Analog Repair: pick your system, and it downloads the latest release, checks it, deletes the old version and starts the app. Download it once; it updates the app from then on.
> **[⬇ Windows](https://github.com/Bratwurstexe/ANALOG_REPAIR/releases/latest/download/Analog-Repair-Launcher-windows-x64.exe)** · **[macOS Apple Silicon](https://github.com/Bratwurstexe/ANALOG_REPAIR/releases/latest/download/Analog-Repair-Launcher-macos-apple-silicon.zip)** · **[macOS Intel](https://github.com/Bratwurstexe/ANALOG_REPAIR/releases/latest/download/Analog-Repair-Launcher-macos-intel.zip)** · **[Linux](https://github.com/Bratwurstexe/ANALOG_REPAIR/releases/latest/download/Analog-Repair-Launcher-linux-x64.tar.gz)**

## Download {TAG}

| Your system | Download | Start |
|---|---|---|
| **Windows** 10 / 11 (64-bit) | **[⬇ Windows (.zip)](https://github.com/Bratwurstexe/ANALOG_REPAIR/releases/download/{TAG}/Analog-Repair-{TAG}-windows-x64.zip)** | `AnalogRepair.Desktop.exe` |
| **macOS**, Apple Silicon (M1 and newer) | **[⬇ macOS Apple Silicon (.zip)](https://github.com/Bratwurstexe/ANALOG_REPAIR/releases/download/{TAG}/Analog-Repair-{TAG}-macos-apple-silicon.zip)** | `Analog Repair.app` |
| **macOS**, Intel | **[⬇ macOS Intel (.zip)](https://github.com/Bratwurstexe/ANALOG_REPAIR/releases/download/{TAG}/Analog-Repair-{TAG}-macos-intel.zip)** | `Analog Repair.app` |
| **Linux** (x64) | **[⬇ Linux AppImage](https://github.com/Bratwurstexe/ANALOG_REPAIR/releases/download/{TAG}/Analog-Repair-{TAG}-linux-x64.AppImage)** | `chmod +x` it, then start it |
| **Linux** (x64), plain folder | **[⬇ Linux folder (.tar.gz)](https://github.com/Bratwurstexe/ANALOG_REPAIR/releases/download/{TAG}/Analog-Repair-{TAG}-linux-x64.tar.gz)** | `./AnalogRepair.Desktop` |

All packages include the app, the video engine and FFmpeg: unpack and start, nothing else to install. [`SHA256SUMS.txt`](https://github.com/Bratwurstexe/ANALOG_REPAIR/releases/download/{TAG}/SHA256SUMS.txt) lists the checksum of every file.

## New in 0.2.0

- **A simpler Repair page that fits on one screen:** start from a preset card (*VHS tape*, *Worn VHS tape*, *Camcorder tape*, *8 mm / Super 8*, *16 mm film*, *Archive, 2× Best*), pick the output size and speed, and find every slider, the source and the date stamp under *Advanced*, folded away by default. Changed values show as *Custom · based on …*; *Save as preset…* keeps them under your own name, and your presets can be renamed, updated or deleted. Presets saved with 0.1.0 appear as your own. Slimmer sliders throughout the app.

Earlier versions: see the [changelog](https://github.com/Bratwurstexe/ANALOG_REPAIR/blob/main/CHANGELOG.md).

## First start

- **Windows:** SmartScreen may warn about an unknown publisher. Choose *More info → Run anyway*.
- **macOS:** the app is not notarised. Right-click it and choose *Open*, or run `xattr -cr "Analog Repair.app"` in Terminal.
- **Linux:** if the file manager does not start it, run `chmod +x AnalogRepair.Desktop` once.

All processing stays on your computer. The application code is MIT licensed. The bundled components keep their own licences: Avalonia (MIT), NumPy (BSD), OpenCV (Apache-2.0) and FFmpeg (GPL, a separate program in the `ffmpeg` folder; source at https://ffmpeg.org/download.html). See `THIRD-PARTY-NOTICES.md` and `ffmpeg/FFMPEG-LICENSE.txt` in the package.
