# Implementation provenance

Analog Repair is a Python video engine (`src/analogrepair/`) with a .NET 8 /
Avalonia desktop application and launcher (`desktop/`).

## Origin

Analog Repair was split off from its sister project
[FPV DVR Cleaner](https://github.com/Bratwurstexe/FPV_DVR_CLEANER) by the same
author and under the same MIT licence. It started from a snapshot of that
code base, in which the repair of tapes and film had been written as a "Movie"
mode. Analog Repair keeps that mode as the whole product and drops what only
served drone footage (the HDZero breakup repair, the analog receiver mode and
the optional locally trained models).

Parts that came with the snapshot and are still used:

| Part | Files | Provenance |
|---|---|---|
| Tape and film stages: deinterlacing, tape noise, flicker, dust and scratches, stabilising, colour bleed | `movie.py` | Written from scratch for the Movie mode, from the problem, public library documentation and measurements on freely licensed test clips. |
| Chroma re-estimation from motion-aligned neighbours | `analog.py` | From FPV DVR Cleaner; its provenance is documented in that project's [INDEPENDENCE.md](https://github.com/Bratwurstexe/FPV_DVR_CLEANER/blob/main/docs/INDEPENDENCE.md). |
| Burned-in overlay detection and refill (here: the date stamp) | `osd.py` | From FPV DVR Cleaner, same record. |
| Fusion and upscaling, GPU path, thread pool, look, trim editor, result assessment, launcher | `upscale.py`, `gpu.py`, `pipeline.py`, `look.py`, `segments.py`, `assess.py`, `desktop/` | Written for FPV DVR Cleaner by the same author, same record. |

## Principles

- **No third-party models or weights.** Every repair is an explicit algorithm
  on NumPy and OpenCV. No neural network, pretrained model, trained weights or
  learned data from anyone else is shipped or downloaded.
- **Everything written for this project** (or its sister project): code,
  constants, data structures, interface texts, the logo and the diagrams.
  Libraries are used through their public APIs only, and are listed in
  [THIRD-PARTY-NOTICES.md](../THIRD-PARTY-NOTICES.md).
- **Example footage is credited.** The images in `docs/media` are made from
  public-domain or freely licensed clips, listed with their licences in
  [media/CREDITS.md](media/CREDITS.md).

## Rules for further work

- Develop from this project's own requirements, freely licensed or own
  footage, public library documentation and measured results.
- Do not bring in code, pseudocode, constants, assets or model files from
  other restoration programs.
- The planned colourisation of black-and-white film follows the same rules:
  an algorithm that spreads colour hints given by the user through a shot,
  with no pretrained colourisation model.

## Licence

The application source is MIT licensed. Bundled and used third-party
components keep their own licences; see
[THIRD-PARTY-NOTICES.md](../THIRD-PARTY-NOTICES.md). This record is not legal
advice.
