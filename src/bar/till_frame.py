"""Till screen layout: margin around till photos and optional frame background.

Drop frame images in NeuroMods/Bar/Till Images/ named tillFrame* (or tillFrame.jpg).
Pick the active frame in till_viewport_tool; saved as frame_image in till_viewport.json.
The till UI is drawn inside the viewport — normalized x, y, width, height within
the frame image's on-screen rect — so the till photo sits inside the monitor area.
border_radius (fraction of min till width/height) rounds the till screen corners.

Tune the viewport visually:
    python -m src.bar.till_viewport_tool
Settings are saved to NeuroMods/Bar/till_viewport.json and loaded by the game.

Without a frame image, a black margin surrounds the till (larger in fullscreen).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Margin as a fraction of min(window width, window height) when no frame image.
MARGIN_FRACTION = 0.05
MARGIN_FRACTION_FULLSCREEN = 0.10

# Default viewport inside the frame image (fractions of the displayed frame rect).
# Override via NeuroMods/Bar/till_viewport.json (edit with till_viewport_tool).
DEFAULT_TILL_VIEWPORT = (0.06, 0.05, 0.88, 0.90)
DEFAULT_TILL_BORDER_RADIUS = 0.0
DEFAULT_TILL_FRAME_IMAGE = "tillFrame.jpg"
TILL_VIEWPORT = DEFAULT_TILL_VIEWPORT
TILL_BORDER_RADIUS = DEFAULT_TILL_BORDER_RADIUS
TILL_FRAME_IMAGE: str | None = DEFAULT_TILL_FRAME_IMAGE

_VIEWPORT_CONFIG_NAME = "till_viewport.json"
_FRAME_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

_LEGACY_FRAME_CANDIDATES = (
    "tillFrame.png",
    "tillFrame.jpg",
    "tillFrame.jpeg",
    "tillFrame.webp",
)


def is_till_view(view_key: str) -> bool:
    return view_key.startswith("till")


def _resolve_till_images_dir(images_dir: Path) -> Path:
    if images_dir.name == "Till Images":
        return images_dir
    return images_dir / "Till Images"


def _get_viewport_config_path(images_dir: Path) -> Path:
    till_dir = _resolve_till_images_dir(images_dir)
    return till_dir.parent / _VIEWPORT_CONFIG_NAME


def discover_till_frame_files(images_dir: Path) -> list[Path]:
    """All tillFrame* image files in Till Images/, sorted by name."""
    till_dir = _resolve_till_images_dir(images_dir)
    if not till_dir.is_dir():
        return []
    frames = [
        path for path in sorted(till_dir.iterdir())
        if path.is_file()
        and path.name.lower().startswith("tillframe")
        and path.suffix.lower() in _FRAME_IMAGE_EXTS
    ]
    return frames


def _default_frame_image_name(images_dir: Path) -> str | None:
    till_dir = _resolve_till_images_dir(images_dir)
    for name in _LEGACY_FRAME_CANDIDATES:
        if (till_dir / name).is_file():
            return name
    frames = discover_till_frame_files(images_dir)
    return frames[0].name if frames else None


def resolve_till_frame_path(images_dir: Path, frame_image: str | None = None) -> Path | None:
    """Resolve configured frame filename to an existing path, with fallbacks."""
    till_dir = _resolve_till_images_dir(images_dir)
    if frame_image:
        path = till_dir / frame_image
        if path.is_file():
            return path
    for name in _LEGACY_FRAME_CANDIDATES:
        path = till_dir / name
        if path.is_file():
            return path
    frames = discover_till_frame_files(images_dir)
    return frames[0] if frames else None


def _clamp_border_radius(value: float) -> float:
    return max(0.0, min(0.5, float(value)))


def load_till_viewport(images_dir: Path | None = None) -> tuple[float, float, float, float, float, str | None]:
    """Load viewport, border radius, and frame image from till_viewport.json."""
    global TILL_VIEWPORT, TILL_BORDER_RADIUS, TILL_FRAME_IMAGE
    if images_dir is None:
        images_dir = Path(__file__).resolve().parent.parent.parent / "NeuroMods" / "Bar"
    config_path = _get_viewport_config_path(images_dir)
    default_frame = _default_frame_image_name(images_dir)
    if not config_path.is_file():
        TILL_VIEWPORT = DEFAULT_TILL_VIEWPORT
        TILL_BORDER_RADIUS = DEFAULT_TILL_BORDER_RADIUS
        TILL_FRAME_IMAGE = default_frame
        return (*TILL_VIEWPORT, TILL_BORDER_RADIUS, TILL_FRAME_IMAGE)
    try:
        import json
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and len(data) == 4:
            x, y, w, h = (float(v) for v in data)
            border_radius = DEFAULT_TILL_BORDER_RADIUS
            frame_image = default_frame
        else:
            x = float(data["x"])
            y = float(data["y"])
            w = float(data.get("width", data.get("w")))
            h = float(data.get("height", data.get("h")))
            border_radius = _clamp_border_radius(
                data.get("border_radius", data.get("borderRadius", DEFAULT_TILL_BORDER_RADIUS)))
            raw_frame = data.get("frame_image", data.get("frameImage"))
            frame_image = str(raw_frame).strip() if raw_frame else default_frame
        TILL_VIEWPORT = (
            max(0.0, min(1.0, x)),
            max(0.0, min(1.0, y)),
            max(0.01, min(1.0, w)),
            max(0.01, min(1.0, h)),
        )
        TILL_BORDER_RADIUS = border_radius
        TILL_FRAME_IMAGE = frame_image
    except (OSError, ValueError, KeyError, TypeError):
        TILL_VIEWPORT = DEFAULT_TILL_VIEWPORT
        TILL_BORDER_RADIUS = DEFAULT_TILL_BORDER_RADIUS
        TILL_FRAME_IMAGE = default_frame
    return (*TILL_VIEWPORT, TILL_BORDER_RADIUS, TILL_FRAME_IMAGE)


def save_till_viewport(
    x: float,
    y: float,
    width: float,
    height: float,
    images_dir: Path,
    *,
    border_radius: float = DEFAULT_TILL_BORDER_RADIUS,
    frame_image: str | None = None,
) -> Path:
    """Write viewport, border radius, and frame image to till_viewport.json."""
    import json
    config_path = _get_viewport_config_path(images_dir)
    payload = {
        "x": round(max(0.0, min(1.0, x)), 4),
        "y": round(max(0.0, min(1.0, y)), 4),
        "width": round(max(0.01, min(1.0, width)), 4),
        "height": round(max(0.01, min(1.0, height)), 4),
        "border_radius": round(_clamp_border_radius(border_radius), 4),
    }
    if frame_image:
        payload["frame_image"] = frame_image
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    global TILL_VIEWPORT, TILL_BORDER_RADIUS, TILL_FRAME_IMAGE
    TILL_VIEWPORT = (payload["x"], payload["y"], payload["width"], payload["height"])
    TILL_BORDER_RADIUS = payload["border_radius"]
    TILL_FRAME_IMAGE = frame_image
    return config_path


def load_till_frame_surface(images_dir: Path, pygame_module, frame_image: str | None = None):
    """Load the configured till frame image from Till Images/, or return None."""
    if frame_image is None:
        frame_image = TILL_FRAME_IMAGE
    path = resolve_till_frame_path(images_dir, frame_image)
    if path is None:
        return None
    return pygame_module.image.load(str(path)).convert()


@dataclass(frozen=True)
class PhotoLayout:
    scaled: object  # pygame.Surface
    blit_x: int
    blit_y: int
    width: int
    height: int
    frame_scaled: object | None = None
    frame_blit_x: int = 0
    frame_blit_y: int = 0
    clip_radius: int = 0


def _clip_radius_pixels(till_w: int, till_h: int, border_radius_fraction: float) -> int:
    if border_radius_fraction <= 0:
        return 0
    return max(0, int(border_radius_fraction * min(till_w, till_h)))


def blit_rounded_surface(dest, surface, x: int, y: int, radius: int, pygame_module=None) -> None:
    """Blit a surface clipped to rounded corners."""
    if radius <= 0:
        dest.blit(surface, (x, y))
        return
    if pygame_module is None:
        import pygame as pygame_module
    w, h = surface.get_size()
    radius = min(radius, w // 2, h // 2)
    if radius <= 0:
        dest.blit(surface, (x, y))
        return
    src = surface if surface.get_flags() & pygame_module.SRCALPHA else surface.convert_alpha()
    mask = pygame_module.Surface((w, h), pygame_module.SRCALPHA)
    pygame_module.draw.rect(mask, (255, 255, 255, 255), (0, 0, w, h), border_radius=radius)
    out = src.copy()
    out.blit(mask, (0, 0), special_flags=pygame_module.BLEND_RGBA_MULT)
    dest.blit(out, (x, y))


def _scale_to_fit(surface, target_w: int, target_h: int, pygame_module):
    src_w, src_h = surface.get_size()
    scale = min(target_w / src_w, target_h / src_h)
    new_w = max(1, int(src_w * scale))
    new_h = max(1, int(src_h * scale))
    scaled = pygame_module.transform.smoothscale(surface, (new_w, new_h))
    x = (target_w - new_w) // 2
    y = (target_h - new_h) // 2
    return scaled, x, y, new_w, new_h


def layout_till_photo(
    till_surface,
    win_w: int,
    win_h: int,
    *,
    is_fullscreen: bool,
    frame_surface=None,
    pygame_module=None,
) -> PhotoLayout:
    """Lay out till photo with frame background or uniform margin."""
    if pygame_module is None:
        import pygame as pygame_module

    if frame_surface is not None:
        frame_scaled, fx, fy, fw, fh = _scale_to_fit(
            frame_surface, win_w, win_h, pygame_module)
        vx, vy, vw, vh = TILL_VIEWPORT
        inner_x = fx + int(vx * fw)
        inner_y = fy + int(vy * fh)
        inner_w = max(1, int(vw * fw))
        inner_h = max(1, int(vh * fh))
        till_scaled, tx, ty, tw, th = _scale_to_fit(
            till_surface, inner_w, inner_h, pygame_module)
        return PhotoLayout(
            scaled=till_scaled,
            blit_x=inner_x + tx,
            blit_y=inner_y + ty,
            width=tw,
            height=th,
            frame_scaled=frame_scaled,
            frame_blit_x=fx,
            frame_blit_y=fy,
            clip_radius=_clip_radius_pixels(tw, th, TILL_BORDER_RADIUS),
        )

    frac = MARGIN_FRACTION_FULLSCREEN if is_fullscreen else MARGIN_FRACTION
    margin = max(12, int(min(win_w, win_h) * frac))
    inner_w = max(1, win_w - margin * 2)
    inner_h = max(1, win_h - margin * 2)
    till_scaled, tx, ty, tw, th = _scale_to_fit(
        till_surface, inner_w, inner_h, pygame_module)
    return PhotoLayout(
        scaled=till_scaled,
        blit_x=margin + tx,
        blit_y=margin + ty,
        width=tw,
        height=th,
        clip_radius=_clip_radius_pixels(tw, th, TILL_BORDER_RADIUS),
    )


def layout_bar_photo(till_surface, win_w: int, win_h: int, pygame_module=None) -> PhotoLayout:
    """Bar position photos: scale to full window (letterboxed)."""
    if pygame_module is None:
        import pygame as pygame_module
    scaled, x, y, w, h = _scale_to_fit(till_surface, win_w, win_h, pygame_module)
    return PhotoLayout(scaled=scaled, blit_x=x, blit_y=y, width=w, height=h)


def layout_view_photo(
    view_key: str,
    surface,
    win_w: int,
    win_h: int,
    *,
    is_fullscreen: bool,
    frame_surface=None,
    pygame_module=None,
) -> PhotoLayout:
    if is_till_view(view_key):
        return layout_till_photo(
            surface, win_w, win_h,
            is_fullscreen=is_fullscreen,
            frame_surface=frame_surface,
            pygame_module=pygame_module,
        )
    return layout_bar_photo(surface, win_w, win_h, pygame_module=pygame_module)