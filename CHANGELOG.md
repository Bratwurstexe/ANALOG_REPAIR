# Changelog

What changed in each release of Analog Repair. The newest release is described on its [release page](https://github.com/Bratwurstexe/ANALOG_REPAIR/releases/latest).

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
