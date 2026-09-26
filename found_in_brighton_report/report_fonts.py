"""Fonts shipped with a declared dependency, available on Streamlit Cloud too."""

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont
import reportlab


@lru_cache(maxsize=64)
def report_font(size: int, bold: bool = False, custom: str | None = None):
    if custom:
        return ImageFont.truetype(custom, size)
    filename = "VeraBd.ttf" if bold else "Vera.ttf"
    bundled = Path(reportlab.__file__).resolve().parent / "fonts" / filename
    return ImageFont.truetype(str(bundled), size)
