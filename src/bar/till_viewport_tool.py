"""
Till viewport calibrator — position till screens inside the frame bezel.

Run with:
    python -m src.bar.till_viewport_tool

Shows your tillFrame.* with a sample till photo fitted inside the viewport,
matching how the game overlays till views on the frame.

Saves to NeuroMods/Bar/till_viewport.json (loaded automatically by the game).

Controls:
- F or click "Choose frame…": open frame picker (all tillFrame* in Till Images)
- Drag empty area on the frame: draw a new viewport rectangle
- Drag inside the yellow viewport: move it
- Drag corner/edge handles: resize
- Arrow keys: nudge position (hold Shift for larger steps)
- Shift + arrow keys on viewport selected: resize width/height
- [ / ] : previous / next sample till image
- Click x, y, width, height, or border_radius to type exact values, Enter to apply
- , / . : decrease / increase border_radius
- S : save
- R : reset viewport + radius to defaults (keeps current frame)
- Ctrl+Q or ESC : quit (picker open: ESC closes picker only)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pygame

from .till_frame import (
    DEFAULT_TILL_BORDER_RADIUS,
    DEFAULT_TILL_VIEWPORT,
    _clip_radius_pixels,
    _default_frame_image_name,
    _scale_to_fit,
    blit_rounded_surface,
    discover_till_frame_files,
    load_till_viewport,
    resolve_till_frame_path,
    save_till_viewport,
)

WIN_W, WIN_H = 1280, 720
SIDEBAR_W = 300
PREVIEW_W = WIN_W - SIDEBAR_W
HANDLE = 12
MIN_FRAC = 0.02
MIN_VIEWPORT_PX = 24

PICKER_W = 620
PICKER_H = 520
PICKER_ROW_H = 76
PICKER_THUMB_W = 108
PICKER_THUMB_H = 60


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent.parent


PROJECT_ROOT = _project_root()
BAR_ROOT = PROJECT_ROOT / "NeuroMods" / "Bar"
IMAGES_DIR = BAR_ROOT / "Till Images"
CONFIG_PATH = BAR_ROOT / "till_viewport.json"


def _discover_sample_tills() -> list[Path]:
    samples = []
    if IMAGES_DIR.is_dir():
        for path in sorted(IMAGES_DIR.glob("till*.jpg")):
            if path.name.lower().startswith("tillframe"):
                continue
            samples.append(path)
    return samples or [IMAGES_DIR / "tillDrinks.jpg"]


def _load_config() -> tuple[tuple[float, float, float, float], float, str | None]:
    default_frame = _default_frame_image_name(BAR_ROOT)
    if CONFIG_PATH.is_file():
        x, y, w, h, border_radius, frame_image = load_till_viewport(BAR_ROOT)
        return (x, y, w, h), border_radius, frame_image
    return DEFAULT_TILL_VIEWPORT, DEFAULT_TILL_BORDER_RADIUS, default_frame


def _load_frame_surface(frame_image: str | None):
    path = resolve_till_frame_path(BAR_ROOT, frame_image)
    if path is None:
        return None
    return pygame.image.load(str(path)).convert()


def _clamp_viewport(x: float, y: float, w: float, h: float) -> tuple[float, float, float, float]:
    w = max(MIN_FRAC, min(1.0, w))
    h = max(MIN_FRAC, min(1.0, h))
    x = max(0.0, min(1.0 - w, x))
    y = max(0.0, min(1.0 - h, y))
    return x, y, w, h


def _frame_layout(frame_surface, preview_w: int, preview_h: int):
    return _scale_to_fit(frame_surface, preview_w, preview_h, pygame)


def _viewport_screen_rect(
    viewport: tuple[float, float, float, float],
    frame_off_x: int,
    frame_off_y: int,
    frame_w: int,
    frame_h: int,
) -> pygame.Rect:
    vx, vy, vw, vh = viewport
    return pygame.Rect(
        frame_off_x + int(vx * frame_w),
        frame_off_y + int(vy * frame_h),
        max(4, int(vw * frame_w)),
        max(4, int(vh * frame_h)),
    )


def _viewport_from_screen_rect(
    rect: pygame.Rect,
    frame_off_x: int,
    frame_off_y: int,
    frame_w: int,
    frame_h: int,
) -> tuple[float, float, float, float]:
    if frame_w <= 0 or frame_h <= 0:
        return DEFAULT_TILL_VIEWPORT
    x = (rect.x - frame_off_x) / frame_w
    y = (rect.y - frame_off_y) / frame_h
    w = rect.width / frame_w
    h = rect.height / frame_h
    return _clamp_viewport(x, y, w, h)


def _frame_bounds_rect(frame_x: int, frame_y: int, frame_w: int, frame_h: int) -> pygame.Rect:
    return pygame.Rect(frame_x, frame_y, frame_w, frame_h)


def _handle_at(mx: int, my: int, rect: pygame.Rect) -> str | None:
    hs = HANDLE
    corners = {
        "nw": pygame.Rect(rect.left - hs // 2, rect.top - hs // 2, hs, hs),
        "ne": pygame.Rect(rect.right - hs // 2, rect.top - hs // 2, hs, hs),
        "sw": pygame.Rect(rect.left - hs // 2, rect.bottom - hs // 2, hs, hs),
        "se": pygame.Rect(rect.right - hs // 2, rect.bottom - hs // 2, hs, hs),
    }
    for name, hr in corners.items():
        if hr.collidepoint(mx, my):
            return name
    edge_pad = hs * 2
    edges = {
        "n": pygame.Rect(rect.left + edge_pad, rect.top - hs // 2, rect.width - edge_pad * 2, hs),
        "s": pygame.Rect(rect.left + edge_pad, rect.bottom - hs // 2, rect.width - edge_pad * 2, hs),
        "w": pygame.Rect(rect.left - hs // 2, rect.top + edge_pad, hs, rect.height - edge_pad * 2),
        "e": pygame.Rect(rect.right - hs // 2, rect.top + edge_pad, hs, rect.height - edge_pad * 2),
    }
    for name, hr in edges.items():
        if hr.width > 0 and hr.height > 0 and hr.collidepoint(mx, my):
            return name
    return None


def _resize_from_handle(
    base: pygame.Rect,
    handle: str,
    mx: int,
    my: int,
    bounds: pygame.Rect,
) -> pygame.Rect:
    """Resize from a fixed anchor edge/corner (base rect at mouse-down)."""
    min_sz = MIN_VIEWPORT_PX

    if handle == "se":
        left, top = base.left, base.top
        right = max(left + min_sz, min(mx, bounds.right))
        bottom = max(top + min_sz, min(my, bounds.bottom))
    elif handle == "nw":
        right, bottom = base.right, base.bottom
        left = min(right - min_sz, max(mx, bounds.left))
        top = min(bottom - min_sz, max(my, bounds.top))
    elif handle == "ne":
        left, bottom = base.left, base.bottom
        right = max(left + min_sz, min(mx, bounds.right))
        top = min(bottom - min_sz, max(my, bounds.top))
    elif handle == "sw":
        right, top = base.right, base.top
        left = min(right - min_sz, max(mx, bounds.left))
        bottom = max(top + min_sz, min(my, bounds.bottom))
    elif handle == "e":
        left, top, bottom = base.left, base.top, base.bottom
        right = max(left + min_sz, min(mx, bounds.right))
    elif handle == "w":
        right, top, bottom = base.right, base.top, base.bottom
        left = min(right - min_sz, max(mx, bounds.left))
    elif handle == "s":
        left, top, right = base.left, base.top, base.right
        bottom = max(top + min_sz, min(my, bounds.bottom))
    elif handle == "n":
        left, bottom, right = base.left, base.bottom, base.right
        top = min(bottom - min_sz, max(my, bounds.top))
    else:
        return base.copy()

    return pygame.Rect(left, top, right - left, bottom - top)


def _move_rect(base: pygame.Rect, mx: int, my: int, anchor: tuple[int, int], bounds: pygame.Rect) -> pygame.Rect:
    dx = mx - anchor[0]
    dy = my - anchor[1]
    out = base.copy()
    out.x = max(bounds.left, min(base.left + dx, bounds.right - out.width))
    out.y = max(bounds.top, min(base.top + dy, bounds.bottom - out.height))
    return out


def _build_frame_thumbnails(frame_paths: list[Path]) -> dict[str, pygame.Surface]:
    thumbs: dict[str, pygame.Surface] = {}
    for path in frame_paths:
        try:
            surf = pygame.image.load(str(path)).convert()
            thumbs[path.name] = pygame.transform.smoothscale(
                surf, (PICKER_THUMB_W, PICKER_THUMB_H))
        except pygame.error:
            continue
    return thumbs


def _picker_geometry() -> tuple[pygame.Rect, pygame.Rect]:
    panel = pygame.Rect(
        (WIN_W - PICKER_W) // 2,
        (WIN_H - PICKER_H) // 2,
        PICKER_W,
        PICKER_H,
    )
    list_rect = pygame.Rect(panel.x + 16, panel.y + 48, panel.width - 32, panel.height - 64)
    return panel, list_rect


def _draw_frame_picker(
    screen,
    *,
    frame_paths: list[Path],
    frame_image: str | None,
    thumbs: dict[str, pygame.Surface],
    scroll_y: int,
    small,
    title,
) -> list[tuple[pygame.Rect, str]]:
    dim = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 170))
    screen.blit(dim, (0, 0))

    panel, list_rect = _picker_geometry()
    pygame.draw.rect(screen, (28, 28, 34), panel, border_radius=8)
    pygame.draw.rect(screen, (90, 90, 100), panel, 2, border_radius=8)
    screen.blit(title.render("Choose frame image", True, (240, 240, 245)), (panel.x + 16, panel.y + 14))
    screen.blit(
        small.render("Click a tillFrame* option — ESC to cancel", True, (160, 160, 170)),
        (panel.x + 16, panel.y + 30),
    )
    pygame.draw.rect(screen, (20, 20, 26), list_rect, border_radius=4)
    pygame.draw.rect(screen, (60, 60, 68), list_rect, 1, border_radius=4)

    clip = screen.get_clip()
    screen.set_clip(list_rect)
    row_hitboxes: list[tuple[pygame.Rect, str]] = []
    content_h = len(frame_paths) * PICKER_ROW_H
    max_scroll = max(0, content_h - list_rect.height)
    scroll_y = max(0, min(scroll_y, max_scroll))

    for i, path in enumerate(frame_paths):
        row_y = list_rect.y + i * PICKER_ROW_H - scroll_y
        if row_y + PICKER_ROW_H < list_rect.y or row_y > list_rect.bottom:
            continue
        row_rect = pygame.Rect(list_rect.x + 4, row_y + 4, list_rect.width - 8, PICKER_ROW_H - 8)
        selected = path.name == frame_image
        fill = (48, 52, 62) if selected else (34, 34, 40)
        pygame.draw.rect(screen, fill, row_rect, border_radius=4)
        border_col = (255, 220, 0) if selected else (70, 70, 78)
        pygame.draw.rect(screen, border_col, row_rect, 2 if selected else 1, border_radius=4)

        thumb_rect = pygame.Rect(row_rect.x + 8, row_rect.y + 6, PICKER_THUMB_W, PICKER_THUMB_H)
        thumb = thumbs.get(path.name)
        if thumb is not None:
            screen.blit(thumb, thumb_rect)
        else:
            pygame.draw.rect(screen, (50, 50, 56), thumb_rect, border_radius=3)

        label_x = thumb_rect.right + 12
        screen.blit(small.render(path.name, True, (235, 235, 240)), (label_x, row_rect.y + 10))
        if selected:
            screen.blit(small.render("current", True, (255, 220, 0)), (label_x, row_rect.y + 30))

        row_hitboxes.append((row_rect, path.name))

    screen.set_clip(clip)
    if content_h > list_rect.height:
        bar_h = max(24, int(list_rect.height * list_rect.height / content_h))
        bar_y = list_rect.y + int(scroll_y / max_scroll * (list_rect.height - bar_h)) if max_scroll else list_rect.y
        pygame.draw.rect(
            screen, (80, 80, 90),
            pygame.Rect(list_rect.right - 8, bar_y, 4, bar_h), border_radius=2)

    return row_hitboxes


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Till Viewport Tool")
    small = pygame.font.SysFont("dejavusans", 14)
    title = pygame.font.SysFont("dejavusans", 20, bold=True)

    frame_paths = discover_till_frame_files(BAR_ROOT)
    if not frame_paths:
        print("No tillFrame* images found in NeuroMods/Bar/Till Images/")
        pygame.quit()
        sys.exit(1)

    viewport, border_radius, frame_image = _load_config()
    if frame_image is None or resolve_till_frame_path(BAR_ROOT, frame_image) is None:
        frame_image = frame_paths[0].name

    frame_surface = _load_frame_surface(frame_image)
    if frame_surface is None:
        print("Could not load frame image.")
        pygame.quit()
        sys.exit(1)

    frame_thumbs = _build_frame_thumbnails(frame_paths)
    samples = _discover_sample_tills()
    sample_idx = 0
    till_surface = pygame.image.load(str(samples[sample_idx])).convert()

    dirty = False
    drag_mode: str | None = None
    drag_anchor = (0, 0)
    drag_base_rect: pygame.Rect | None = None
    drag_start_rect: pygame.Rect | None = None
    editing_field: str | None = None
    edit_text = ""
    show_frame_picker = False
    picker_scroll = 0
    frame_button_rect = pygame.Rect(0, 0, 0, 0)
    picker_row_hitboxes: list[tuple[pygame.Rect, str]] = []

    frame_scaled, frame_x, frame_y, frame_w, frame_h = _frame_layout(
        frame_surface, PREVIEW_W, WIN_H)

    def _apply_frame_choice(name: str) -> None:
        nonlocal frame_image, frame_surface, frame_scaled, frame_x, frame_y, frame_w, frame_h, dirty
        new_surface = _load_frame_surface(name)
        if new_surface is None:
            return
        frame_image = name
        frame_surface = new_surface
        frame_scaled, frame_x, frame_y, frame_w, frame_h = _frame_layout(
            frame_surface, PREVIEW_W, WIN_H)
        dirty = True

    running = True
    while running:
        mx, my = pygame.mouse.get_pos()
        in_preview = mx < PREVIEW_W and not show_frame_picker
        vp_rect = _viewport_screen_rect(viewport, frame_x, frame_y, frame_w, frame_h)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if show_frame_picker:
                    if event.key == pygame.K_ESCAPE:
                        show_frame_picker = False
                    continue
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_q and (event.mod & pygame.KMOD_CTRL):
                    running = False
                elif event.key == pygame.K_f:
                    show_frame_picker = True
                    picker_scroll = 0
                elif event.key == pygame.K_s:
                    save_till_viewport(
                        *viewport,
                        BAR_ROOT,
                        border_radius=border_radius,
                        frame_image=frame_image,
                    )
                    dirty = False
                    print(f"Saved {CONFIG_PATH}")
                elif event.key == pygame.K_r:
                    viewport = DEFAULT_TILL_VIEWPORT
                    border_radius = DEFAULT_TILL_BORDER_RADIUS
                    dirty = True
                elif event.key == pygame.K_COMMA:
                    border_radius = max(0.0, border_radius - 0.005)
                    dirty = True
                elif event.key == pygame.K_PERIOD:
                    border_radius = min(0.5, border_radius + 0.005)
                    dirty = True
                elif event.key == pygame.K_LEFTBRACKET:
                    sample_idx = (sample_idx - 1) % len(samples)
                    till_surface = pygame.image.load(str(samples[sample_idx])).convert()
                elif event.key == pygame.K_RIGHTBRACKET:
                    sample_idx = (sample_idx + 1) % len(samples)
                    till_surface = pygame.image.load(str(samples[sample_idx])).convert()
                elif editing_field:
                    if event.key == pygame.K_RETURN:
                        try:
                            val = float(edit_text.strip())
                            x, y, w, h = viewport
                            if editing_field == "x":
                                viewport = _clamp_viewport(val, y, w, h)
                            elif editing_field == "y":
                                viewport = _clamp_viewport(x, val, w, h)
                            elif editing_field == "width":
                                viewport = _clamp_viewport(x, y, val, h)
                            elif editing_field == "height":
                                viewport = _clamp_viewport(x, y, w, val)
                            elif editing_field == "border_radius":
                                border_radius = max(0.0, min(0.5, val))
                            dirty = True
                        except ValueError:
                            pass
                        editing_field = None
                        edit_text = ""
                    elif event.key == pygame.K_BACKSPACE:
                        edit_text = edit_text[:-1]
                    elif event.unicode and (event.unicode.isdigit() or event.unicode in ".-"):
                        edit_text += event.unicode
                elif in_preview:
                    step = 0.005 if event.mod & pygame.KMOD_SHIFT else 0.001
                    x, y, w, h = viewport
                    if event.mod & pygame.KMOD_SHIFT and event.key in (
                        pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN,
                    ):
                        if event.key == pygame.K_LEFT:
                            viewport = _clamp_viewport(x, y, w - step, h)
                        elif event.key == pygame.K_RIGHT:
                            viewport = _clamp_viewport(x, y, w + step, h)
                        elif event.key == pygame.K_UP:
                            viewport = _clamp_viewport(x, y, w, h - step)
                        elif event.key == pygame.K_DOWN:
                            viewport = _clamp_viewport(x, y, w, h + step)
                        dirty = True
                    elif event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
                        if event.key == pygame.K_LEFT:
                            viewport = _clamp_viewport(x - step, y, w, h)
                        elif event.key == pygame.K_RIGHT:
                            viewport = _clamp_viewport(x + step, y, w, h)
                        elif event.key == pygame.K_UP:
                            viewport = _clamp_viewport(x, y - step, w, h)
                        elif event.key == pygame.K_DOWN:
                            viewport = _clamp_viewport(x, y + step, w, h)
                        dirty = True
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                click_x, click_y = event.pos
                if show_frame_picker:
                    for row_rect, name in picker_row_hitboxes:
                        if row_rect.collidepoint(click_x, click_y):
                            _apply_frame_choice(name)
                            show_frame_picker = False
                            break
                    else:
                        panel, _ = _picker_geometry()
                        if not panel.collidepoint(click_x, click_y):
                            show_frame_picker = False
                elif frame_button_rect.collidepoint(click_x, click_y):
                    show_frame_picker = True
                    picker_scroll = 0
                elif click_x >= PREVIEW_W:
                    field_boxes = getattr(main, "_field_boxes", {})
                    for name, box in field_boxes.items():
                        if box.collidepoint(click_x, click_y):
                            editing_field = name
                            edit_text = ""
                            break
                elif click_x < PREVIEW_W and not show_frame_picker:
                    handle = _handle_at(click_x, click_y, vp_rect)
                    drag_base_rect = vp_rect.copy()
                    drag_anchor = (click_x, click_y)
                    if handle:
                        drag_mode = handle
                    elif vp_rect.collidepoint(click_x, click_y):
                        drag_mode = "move"
                    else:
                        drag_mode = "draw"
                        drag_start_rect = pygame.Rect(click_x, click_y, 0, 0)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                drag_mode = None
                drag_base_rect = None
                drag_start_rect = None
            elif event.type == pygame.MOUSEMOTION and drag_mode and not show_frame_picker:
                motion_x, motion_y = event.pos
                if motion_x >= PREVIEW_W:
                    continue
                frame_bounds = _frame_bounds_rect(frame_x, frame_y, frame_w, frame_h)
                if drag_mode == "draw" and drag_start_rect is not None:
                    sx, sy = drag_anchor
                    drag_start_rect = pygame.Rect(
                        min(sx, motion_x), min(sy, motion_y),
                        abs(motion_x - sx), abs(motion_y - sy))
                    viewport = _viewport_from_screen_rect(
                        drag_start_rect, frame_x, frame_y, frame_w, frame_h)
                    dirty = True
                elif drag_mode == "move" and drag_base_rect is not None:
                    new_rect = _move_rect(
                        drag_base_rect, motion_x, motion_y, drag_anchor, frame_bounds)
                    viewport = _viewport_from_screen_rect(
                        new_rect, frame_x, frame_y, frame_w, frame_h)
                    dirty = True
                elif drag_base_rect is not None:
                    new_rect = _resize_from_handle(
                        drag_base_rect, drag_mode, motion_x, motion_y, frame_bounds)
                    viewport = _viewport_from_screen_rect(
                        new_rect, frame_x, frame_y, frame_w, frame_h)
                    dirty = True
            elif event.type == pygame.MOUSEWHEEL and show_frame_picker:
                _, list_rect = _picker_geometry()
                content_h = len(frame_paths) * PICKER_ROW_H
                max_scroll = max(0, content_h - list_rect.height)
                picker_scroll = max(0, min(picker_scroll - event.y * 24, max_scroll))

        # --- draw ---
        screen.fill((18, 18, 22))
        screen.blit(frame_scaled, (frame_x, frame_y))

        vx, vy, vw, vh = viewport
        inner_x = frame_x + int(vx * frame_w)
        inner_y = frame_y + int(vy * frame_h)
        inner_w = max(1, int(vw * frame_w))
        inner_h = max(1, int(vh * frame_h))
        till_scaled, tx, ty, tw, th = _scale_to_fit(
            till_surface, inner_w, inner_h, pygame)
        till_x = inner_x + tx
        till_y = inner_y + ty
        clip_radius = _clip_radius_pixels(tw, th, border_radius)
        blit_rounded_surface(screen, till_scaled, till_x, till_y, clip_radius, pygame)

        overlay = pygame.Surface((inner_w, inner_h), pygame.SRCALPHA)
        overlay.fill((255, 220, 0, 35))
        screen.blit(overlay, (inner_x, inner_y))
        pygame.draw.rect(screen, (255, 220, 0), vp_rect, 2)
        if clip_radius > 0:
            pygame.draw.rect(
                screen, (255, 220, 0),
                pygame.Rect(till_x, till_y, tw, th), 1, border_radius=clip_radius)

        for hx, hy in (
            (vp_rect.left, vp_rect.top),
            (vp_rect.right, vp_rect.top),
            (vp_rect.left, vp_rect.bottom),
            (vp_rect.right, vp_rect.bottom),
            (vp_rect.centerx, vp_rect.top),
            (vp_rect.centerx, vp_rect.bottom),
            (vp_rect.left, vp_rect.centery),
            (vp_rect.right, vp_rect.centery),
        ):
            pygame.draw.rect(
                screen, (255, 255, 255),
                pygame.Rect(hx - HANDLE // 2, hy - HANDLE // 2, HANDLE, HANDLE), 1)
            pygame.draw.rect(
                screen, (255, 220, 0),
                pygame.Rect(hx - HANDLE // 2 + 1, hy - HANDLE // 2 + 1, HANDLE - 2, HANDLE - 2))

        pygame.draw.line(screen, (50, 50, 58), (PREVIEW_W, 0), (PREVIEW_W, WIN_H), 2)

        sx = PREVIEW_W + 16
        sy = 16
        screen.blit(title.render("Till viewport", True, (240, 240, 245)), (sx, sy))
        sy += 32

        frame_button_rect = pygame.Rect(sx, sy, SIDEBAR_W - 32, 30)
        pygame.draw.rect(screen, (42, 42, 50), frame_button_rect, border_radius=4)
        pygame.draw.rect(screen, (255, 220, 0), frame_button_rect, 1, border_radius=4)
        screen.blit(small.render("Choose frame…  (F)", True, (240, 240, 245)), (sx + 8, sy + 7))
        sy += 38

        frame_label = frame_image or "(none)"
        if len(frame_label) > 34:
            frame_label = "…" + frame_label[-33:]
        screen.blit(small.render(f"Frame: {frame_label}", True, (140, 200, 140)), (sx, sy))
        sy += 22

        lines = [
            "Fractions are relative to the",
            "displayed frame image (0–1).",
            "",
            "Drag on frame: new rect",
            "Drag yellow area: move",
            "Drag handles: resize",
            "Arrows: nudge position",
            "Shift+arrows: resize",
            ", / .: border radius",
            "[ / ]: sample till image",
            "S: save   R: reset",
            "Ctrl+Q / ESC: quit",
        ]
        for line in lines:
            screen.blit(small.render(line, True, (170, 170, 180)), (sx, sy))
            sy += 18

        sy += 8
        field_boxes: dict[str, pygame.Rect] = {}
        labels = (
            ("x", vx, "{:.4f}"),
            ("y", vy, "{:.4f}"),
            ("width", vw, "{:.4f}"),
            ("height", vh, "{:.4f}"),
            ("border_radius", border_radius, "{:.4f}"),
        )
        for name, val, fmt in labels:
            label = "radius:" if name == "border_radius" else f"{name}:"
            screen.blit(small.render(label, True, (200, 200, 210)), (sx, sy + 2))
            box = pygame.Rect(sx + 72, sy, SIDEBAR_W - 96, 24)
            pygame.draw.rect(screen, (40, 40, 48), box, border_radius=3)
            border_col = (255, 220, 0) if editing_field == name else (90, 90, 100)
            pygame.draw.rect(screen, border_col, box, 1, border_radius=3)
            shown = edit_text if editing_field == name else fmt.format(val)
            screen.blit(small.render(shown, True, (255, 255, 255)), (box.x + 6, box.y + 4))
            field_boxes[name] = box
            sy += 30
        sy += 2
        screen.blit(
            small.render(
                f"radius px @ preview: {_clip_radius_pixels(tw, th, border_radius)}",
                True, (140, 140, 155)),
            (sx, sy))
        sy += 18
        main._field_boxes = field_boxes

        sy += 8
        sample_name = samples[sample_idx].name if samples else "(none)"
        screen.blit(small.render(f"Sample: {sample_name}", True, (140, 200, 140)), (sx, sy))
        sy += 22
        status = "unsaved changes" if dirty else "saved"
        screen.blit(small.render(status, True, (220, 180, 80) if dirty else (120, 180, 120)), (sx, sy))

        if show_frame_picker:
            picker_row_hitboxes = _draw_frame_picker(
                screen,
                frame_paths=frame_paths,
                frame_image=frame_image,
                thumbs=frame_thumbs,
                scroll_y=picker_scroll,
                small=small,
                title=title,
            )

        pygame.display.flip()

    if dirty:
        print("Unsaved viewport changes — run again and press S to save, or edit till_viewport.json manually.")
    pygame.quit()


if __name__ == "__main__":
    main()