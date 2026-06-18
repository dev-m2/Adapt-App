"""Customer screen background, portrait viewport, roster, and U-shaped overlay layout."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

_FRAME_CANDIDATES = (
    "customerFrame.png",
    "customerFrame.jpg",
    "customerFrame.jpeg",
    "customerFrame.webp",
)

_CUSTOMER_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
_ROSTER_NAME = "customers.txt"
_VIEWPORT_CONFIG_NAME = "customer_viewport.json"

# Portrait area on the customer screen (fractions of the window).
DEFAULT_CUSTOMER_VIEWPORT = (0.38, 0.05, 0.24, 0.30)
DEFAULT_NAME_GAP = 6
DEFAULT_NAME_HEIGHT = 28
NAME_LABEL_ALPHA = int(255 * 0.7)

CUSTOMER_VIEWPORT = DEFAULT_CUSTOMER_VIEWPORT
CUSTOMER_NAME_GAP = DEFAULT_NAME_GAP
CUSTOMER_NAME_HEIGHT = DEFAULT_NAME_HEIGHT


@dataclass(frozen=True)
class CustomerLayout:
    placed_box: tuple[int, int, int, int]
    sent_box: tuple[int, int, int, int]
    demands_box: tuple[int, int, int, int]
    grade_again: tuple[int, int, int, int]
    grade_hard: tuple[int, int, int, int]
    grade_good: tuple[int, int, int, int]
    grade_easy: tuple[int, int, int, int]
    reset_placed: tuple[int, int, int, int]
    reset_till: tuple[int, int, int, int]
    finish_button: tuple[int, int, int, int]
    demands_text_width: int


@dataclass(frozen=True)
class CustomerEntry:
    display_name: str
    image_file: str


def _bar_root_from_images_dir(images_dir: Path) -> Path:
    if images_dir.name == "Bar Images":
        return images_dir.parent
    if images_dir.name == "Till Images":
        return images_dir.parent
    if images_dir.name == "Customer Images":
        return images_dir.parent
    return images_dir


def _bar_images_dir(images_dir: Path) -> Path:
    root = _bar_root_from_images_dir(images_dir)
    return root / "Bar Images"


def AIgetCustomerImagesDir(images_dir: Path) -> Path:
    return _bar_root_from_images_dir(images_dir) / "Customer Images"


def _get_viewport_config_path(images_dir: Path) -> Path:
    return _bar_root_from_images_dir(images_dir) / _VIEWPORT_CONFIG_NAME


def _get_roster_path(images_dir: Path) -> Path:
    return _bar_root_from_images_dir(images_dir) / _ROSTER_NAME


def load_customer_viewport(
    images_dir: Path | None = None,
) -> tuple[float, float, float, float, int, int]:
    """Load portrait viewport fractions and name label spacing from JSON."""
    global CUSTOMER_VIEWPORT, CUSTOMER_NAME_GAP, CUSTOMER_NAME_HEIGHT
    if images_dir is None:
        images_dir = Path(__file__).resolve().parent.parent.parent / "NeuroMods" / "Bar"
    config_path = _get_viewport_config_path(images_dir)
    if not config_path.is_file():
        CUSTOMER_VIEWPORT = DEFAULT_CUSTOMER_VIEWPORT
        CUSTOMER_NAME_GAP = DEFAULT_NAME_GAP
        CUSTOMER_NAME_HEIGHT = DEFAULT_NAME_HEIGHT
        return (*CUSTOMER_VIEWPORT, CUSTOMER_NAME_GAP, CUSTOMER_NAME_HEIGHT)
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        x = float(data["x"])
        y = float(data["y"])
        w = float(data.get("width", data.get("w")))
        h = float(data.get("height", data.get("h")))
        name_gap = int(data.get("name_gap", data.get("nameGap", DEFAULT_NAME_GAP)))
        name_height = int(data.get("name_height", data.get("nameHeight", DEFAULT_NAME_HEIGHT)))
        CUSTOMER_VIEWPORT = (
            max(0.0, min(1.0, x)),
            max(0.0, min(1.0, y)),
            max(0.02, min(1.0, w)),
            max(0.02, min(1.0, h)),
        )
        CUSTOMER_NAME_GAP = max(0, name_gap)
        CUSTOMER_NAME_HEIGHT = max(18, name_height)
    except (OSError, ValueError, KeyError, TypeError):
        CUSTOMER_VIEWPORT = DEFAULT_CUSTOMER_VIEWPORT
        CUSTOMER_NAME_GAP = DEFAULT_NAME_GAP
        CUSTOMER_NAME_HEIGHT = DEFAULT_NAME_HEIGHT
    return (*CUSTOMER_VIEWPORT, CUSTOMER_NAME_GAP, CUSTOMER_NAME_HEIGHT)


def save_customer_viewport(
    x: float,
    y: float,
    width: float,
    height: float,
    images_dir: Path,
    *,
    name_gap: int = DEFAULT_NAME_GAP,
    name_height: int = DEFAULT_NAME_HEIGHT,
) -> Path:
    """Write portrait viewport settings to customer_viewport.json."""
    config_path = _get_viewport_config_path(images_dir)
    payload = {
        "x": round(max(0.0, min(1.0, x)), 4),
        "y": round(max(0.0, min(1.0, y)), 4),
        "width": round(max(0.02, min(1.0, width)), 4),
        "height": round(max(0.02, min(1.0, height)), 4),
        "name_gap": max(0, int(name_gap)),
        "name_height": max(18, int(name_height)),
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    global CUSTOMER_VIEWPORT, CUSTOMER_NAME_GAP, CUSTOMER_NAME_HEIGHT
    CUSTOMER_VIEWPORT = (
        payload["x"], payload["y"], payload["width"], payload["height"])
    CUSTOMER_NAME_GAP = payload["name_gap"]
    CUSTOMER_NAME_HEIGHT = payload["name_height"]
    return config_path


def AIloadCustomerRoster(images_dir: Path) -> list[CustomerEntry]:
    """Parse customers.txt into display name + image filename pairs."""
    roster_path = _get_roster_path(images_dir)
    customer_dir = AIgetCustomerImagesDir(images_dir)
    if not roster_path.is_file():
        entries: list[CustomerEntry] = []
        if customer_dir.is_dir():
            for path in sorted(customer_dir.iterdir()):
                if path.suffix.lower() in _CUSTOMER_IMAGE_EXTS:
                    entries.append(CustomerEntry(path.stem, path.name))
        return entries

    entries = []
    for raw_line in roster_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            display_name, image_file = line.split("=", 1)
            display_name = display_name.strip()
            image_file = image_file.strip()
        else:
            image_file = line
            display_name = Path(image_file).stem
        if display_name and image_file:
            entries.append(CustomerEntry(display_name, image_file))
    return entries


def AIresolveCustomerImagePath(images_dir: Path, image_file: str) -> Path | None:
    path = AIgetCustomerImagesDir(images_dir) / image_file
    return path if path.is_file() else None


def load_customer_headshot_surface(images_dir: Path, image_file: str, pygame_module):
    path = AIresolveCustomerImagePath(images_dir, image_file)
    if path is None:
        return None
    surf = pygame_module.image.load(str(path))
    if path.suffix.lower() == ".png":
        return surf.convert_alpha()
    return surf.convert()


def AIpickRandomCustomer(
    roster: list[CustomerEntry],
    *,
    exclude_name: str | None = None,
) -> CustomerEntry | None:
    if not roster:
        return None
    pool = roster
    if exclude_name and len(roster) > 1:
        filtered = [c for c in roster if c.display_name != exclude_name]
        if filtered:
            pool = filtered
    return random.choice(pool)


def load_customer_frame_surface(images_dir: Path, pygame_module):
    """Load optional customerFrame.* from Bar Images/, or return None."""
    bar_dir = _bar_images_dir(images_dir)
    for name in _FRAME_CANDIDATES:
        path = bar_dir / name
        if path.is_file():
            return pygame_module.image.load(str(path)).convert()
    return None


def AIcomputeCustomerLayout(win_w: int, win_h: int) -> CustomerLayout:
    """U-shaped UI: empty top centre; side columns; demands/report along the bottom."""
    margin = max(14, int(min(win_w, win_h) * 0.022))
    top_gap = int(win_h * 0.30)
    col_w = min(300, max(155, int(win_w * 0.21)))
    left_x = margin
    right_x = win_w - margin - col_w

    btn_h = 36
    btn_gap = 4
    btn_reset_h = 38

    box_y = top_gap + margin
    side_stack_h = win_h - box_y - margin
    box_h = max(96, int(side_stack_h * 0.36))
    controls_top = box_y + box_h + 10
    grade_start_y = controls_top + 18

    placed_box = (left_x, box_y, col_w, box_h)
    sent_box = (right_x, box_y, col_w, box_h)

    grade_again = (left_x, grade_start_y, col_w, btn_h)
    grade_hard = (left_x, grade_start_y + (btn_h + btn_gap), col_w, btn_h)
    grade_good = (left_x, grade_start_y + 2 * (btn_h + btn_gap), col_w, btn_h)
    grade_easy = (left_x, grade_start_y + 3 * (btn_h + btn_gap), col_w, btn_h)
    reset_placed = (left_x, grade_start_y + 4 * (btn_h + btn_gap) + 8, col_w, btn_reset_h)

    right_controls_top = box_y + box_h + 12
    reset_till = (right_x, right_controls_top, col_w, btn_reset_h)
    finish_button = (
        right_x, right_controls_top + btn_reset_h + 10, col_w, btn_reset_h)

    dem_w = max(300, win_w - 2 * (col_w + 2 * margin))
    dem_x = (win_w - dem_w) // 2
    dem_top = box_y + box_h + margin
    dem_h = max(120, win_h - dem_top - margin)
    dem_y = dem_top
    demands_box = (dem_x, dem_y, dem_w, dem_h)
    dem_pad_x = 12
    demands_text_width = dem_w - 2 * dem_pad_x

    return CustomerLayout(
        placed_box=placed_box,
        sent_box=sent_box,
        demands_box=demands_box,
        grade_again=grade_again,
        grade_hard=grade_hard,
        grade_good=grade_good,
        grade_easy=grade_easy,
        reset_placed=reset_placed,
        reset_till=reset_till,
        finish_button=finish_button,
        demands_text_width=demands_text_width,
    )


def _viewport_screen_rect(
    viewport: tuple[float, float, float, float],
    win_w: int,
    win_h: int,
) -> tuple[int, int, int, int]:
    vx, vy, vw, vh = viewport
    return (
        int(vx * win_w),
        int(vy * win_h),
        max(8, int(vw * win_w)),
        max(8, int(vh * win_h)),
    )


def AIdrawCustomerBackground(
    screen,
    frame_surface,
    win_w: int,
    win_h: int,
    pygame_module,
) -> None:
    """Draw customer frame scaled to the window (letterboxed)."""
    from . import ui_theme
    from .till_frame import _scale_to_fit

    screen.fill(ui_theme.BG_LETTERBOX)
    if frame_surface is None:
        screen.fill(ui_theme.CUSTOMER_BG)
        return
    scaled, x, y, _w, _h = _scale_to_fit(frame_surface, win_w, win_h, pygame_module)
    screen.blit(scaled, (x, y))


def AIdrawCustomerPortrait(
    screen,
    headshot_surface,
    display_name: str,
    font,
    win_w: int,
    win_h: int,
    pygame_module,
    *,
    viewport: tuple[float, float, float, float] | None = None,
    name_gap: int | None = None,
    name_height: int | None = None,
) -> None:
    """Draw transparent headshot in the viewport with name label underneath."""
    from . import ui_theme
    from .till_frame import _scale_to_fit

    if headshot_surface is None or not display_name:
        return

    vx, vy, vw, vh = viewport or CUSTOMER_VIEWPORT
    gap = CUSTOMER_NAME_GAP if name_gap is None else name_gap
    label_h = CUSTOMER_NAME_HEIGHT if name_height is None else name_height

    px, py, pw, ph = _viewport_screen_rect((vx, vy, vw, vh), win_w, win_h)
    scaled, ox, oy, sw, sh = _scale_to_fit(headshot_surface, pw, ph, pygame_module)
    draw_x = px + ox
    draw_y = py + oy
    screen.blit(scaled, (draw_x, draw_y))

    name_surf = font.render(display_name, True, ui_theme.PANEL_HEADER)
    pad_x = 10
    pad_y = 4
    bg_w = name_surf.get_width() + 2 * pad_x
    bg_h = max(label_h, name_surf.get_height() + 2 * pad_y)
    bg_x = px + (pw - bg_w) // 2
    bg_y = py + ph + gap

    label_bg = pygame_module.Surface((bg_w, bg_h), pygame_module.SRCALPHA)
    pygame_module.draw.rect(
        label_bg, (*ui_theme.GUI_DARK, NAME_LABEL_ALPHA), (0, 0, bg_w, bg_h), border_radius=4)
    pygame_module.draw.rect(
        label_bg, (*ui_theme.PANEL_BORDER, min(255, NAME_LABEL_ALPHA + 30)),
        (0, 0, bg_w, bg_h), 1, border_radius=4)
    screen.blit(label_bg, (bg_x, bg_y))
    text_x = bg_x + (bg_w - name_surf.get_width()) // 2
    text_y = bg_y + (bg_h - name_surf.get_height()) // 2
    screen.blit(name_surf, (text_x, text_y))