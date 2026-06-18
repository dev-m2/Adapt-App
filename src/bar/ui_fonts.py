"""Shared UI fonts for bar pygame tools (clear i vs I, compact like default)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

# pygame SysFont(None) is a small bitmap face (i/I/L look alike). Proportional
# fonts at the same point size render taller/wider — scale down to match layout.
_SCALED_SIZES: dict[int, int] = {
    28: 19,
    24: 17,
    20: 14,
    18: 13,
    15: 11,
    14: 10,
}

# Known paths (Fedora puts Liberation here; Noto under google-noto/).
_FONT_PATHS: tuple[str, ...] = (
    "/usr/share/fonts/liberation-sans-fonts/LiberationSans-Regular.ttf",
    "/usr/share/fonts/google-noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
)

_SYS_FALLBACKS: tuple[str, ...] = (
    "liberation sans",
    "noto sans",
    "dejavusans",
    "freesans",
    "arial",
)

# fc-match names to try when paths above are missing (works on Fedora, etc.)
_FC_MATCH_NAMES: tuple[str, ...] = (
    "Liberation Sans:style=Regular",
    "Noto Sans:style=Regular",
    "DejaVu Sans:style=Book",
    "sans",
)


def _scaled_size(requested: int) -> int:
    return _SCALED_SIZES.get(requested, max(8, round(requested * 0.72)))


def _resolve_font_file() -> str | None:
    for path in _FONT_PATHS:
        if Path(path).is_file():
            return path

    if not shutil.which("fc-match"):
        return None

    for pattern in _FC_MATCH_NAMES:
        try:
            out = subprocess.check_output(
                ["fc-match", "-f", "%{file}", pattern],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        except (subprocess.CalledProcessError, OSError):
            continue
        if out and Path(out).is_file():
            return out
    return None


def ui_font(size: int, bold: bool = False):
    """Proportional UI font: readable i/I, bullet support, ~default bitmap size.

    On Fedora, install if missing: ``sudo dnf install liberation-sans-fonts``
    """
    import pygame

    px = _scaled_size(size)
    path = _resolve_font_file()
    if path:
        return pygame.font.Font(path, px)

    return pygame.font.SysFont(list(_SYS_FALLBACKS), px, bold=bold)


def font_status() -> str:
    """One-line summary of which UI font file is in use (for debugging)."""
    path = _resolve_font_file()
    if path:
        return f"UI font: {path}"
    return "UI font: SysFont fallback (install liberation-sans-fonts on Fedora)"