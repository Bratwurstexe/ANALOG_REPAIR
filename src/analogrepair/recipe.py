from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path


# Output file formats and the file extension each one is written with.
DATEIFORMATE = {"mp4-h264": ".mp4", "mp4-hevc": ".mp4", "mov-prores": ".mov",
                "mkv-h264": ".mkv", "webm-vp9": ".webm"}
# Strengths of the finishing look, each 0..1: colour grade, glow, lens fringe,
# vignette and film grain. See look.py.
LOOK_WERTE = ("look_farbstimmung", "look_leuchten", "look_farbsaum", "look_vignette", "look_koernung")
# The repairs of tapes and film, each 0..100: stabilising, flicker, dust and
# scratches, tape noise (tracking bands, head switch, line jitter). See movie.py.
FILM_WERTE = ("stabilisierung", "flackerausgleich", "staubentfernung", "bandstoerung")
# The source: a tape (VHS, S-VHS, Hi8, Video8, camcorder) or film (8 mm, Super 8,
# 16 mm). Both run the same chain; the presets of the app differ.
SIGNALARTEN = {"tape", "film"}
# Fields a saved recipe may lack; they load with their defaults.
SPAETERE_FELDER = {"aufwand", "dateiformat", "look", *LOOK_WERTE, *FILM_WERTE, "koernung_behalten"}


@dataclass(frozen=True)
class Arbeitsrezept:
    """User intent, independent from any FFmpeg command syntax."""

    signalart: str = "tape"
    farbberuhigung: int = 35
    kantendetail: int = 15
    vergroesserung_prozent: int = 100
    bewegungsspur: int = 0
    schnittbeginn: float = 0.0
    schnittende: float = 0.0
    untertiteltext: str = ""
    kompressionswert: int = 20
    dateiziel_mb: int = 0
    osd_entfernen: bool = False
    rauschminderung: int = 0
    aufwand: str = "balanced"
    dateiformat: str = "mp4-h264"
    look: bool = False
    look_farbstimmung: float = 0.0
    look_leuchten: float = 0.0
    look_farbsaum: float = 0.0
    look_vignette: float = 0.0
    look_koernung: float = 0.0
    stabilisierung: int = 0
    flackerausgleich: int = 0
    staubentfernung: int = 0
    bandstoerung: int = 0
    koernung_behalten: bool = False

    def validate(self) -> None:
        if self.signalart not in SIGNALARTEN:
            raise ValueError("Unknown source: choose tape or film")
        for name in ("farbberuhigung", "kantendetail", "bewegungsspur", "rauschminderung"):
            if not 0 <= getattr(self, name) <= 100:
                raise ValueError(f"{name} must be between 0 and 100")
        if self.vergroesserung_prozent not in {100, 150, 200}:
            raise ValueError("Invalid target size")
        if self.schnittbeginn < 0 or self.schnittende < 0:
            raise ValueError("Cut times cannot be negative")
        if self.schnittende and self.schnittende <= self.schnittbeginn:
            raise ValueError("The out point must follow the in point")
        if not 14 <= self.kompressionswert <= 32:
            raise ValueError("Quality must be between 14 and 32")
        if self.dateiziel_mb < 0:
            raise ValueError("Size cap cannot be negative")
        if len(self.untertiteltext) > 300:
            raise ValueError("Caption is too long")
        if not isinstance(self.osd_entfernen, bool):
            raise ValueError("Date stamp removal must be on or off")
        if self.aufwand not in {"fast", "balanced", "best"}:
            raise ValueError("Unknown processing effort")
        if self.dateiformat not in DATEIFORMATE:
            raise ValueError("Unknown file format")
        if not isinstance(self.look, bool):
            raise ValueError("The look must be on or off")
        for name in LOOK_WERTE:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        for name in FILM_WERTE:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
                raise ValueError(f"{name} must be a whole number between 0 and 100")
        if not isinstance(self.koernung_behalten, bool):
            raise ValueError("Keeping the film grain must be on or off")

    def save(self, path: Path) -> None:
        self.validate()
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Arbeitsrezept:
        data = json.loads(path.read_text(encoding="utf-8"))
        # Recipes that leave out the later settings still load with their defaults.
        if (not isinstance(data, dict) or not set(data) <= set(cls.__dataclass_fields__)
                or set(cls.__dataclass_fields__) - set(data) - SPAETERE_FELDER):
            raise ValueError("Incomplete or unknown recipe")
        recipe = cls(**data)
        recipe.validate()
        return recipe
