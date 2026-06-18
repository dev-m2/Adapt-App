"""
Customer portrait viewport calibrator — position the headshot area on the customer screen.

Run with:
    python -m src.bar.customer_viewport_tool

Saves to NeuroMods/Bar/customer_viewport.json (loaded automatically by the game).

Controls:
- Drag empty area: draw a new viewport rectangle
- Drag inside yellow viewport: move it
- Drag corner/edge handles: resize
- Arrow keys: nudge (Shift = larger steps)
- Shift + arrows: resize width/height
- [ / ] : previous / next sample customer headshot
- Click x, y, width, height, name_gap to type values (Enter to apply)
- S : save
- R : reset to defaults
- Ctrl+Q or ESC : quit
"""

from __future__ import annotations

import sys
from pathlib import Path

import pygame

from .customer_screen import (
    AIgetCustomerImagesDir,
    AIloadCustomerRoster,
    AIresolveCustomerImagePath,
    DEFAULT_CUSTOMER_VIEWPORT,
    DEFAULT_NAME_GAP,
    DEFAULT_NAME_HEIGHT,
    load_customer_frame_surface,
    load_customer_viewport,
    save_customer_viewport,
)
from .till_frame import _scale_to_fit

WIN_W, WIN_H = 1280, 720
SIDEBAR_W = 300
PREVIEW_W = WIN_W - SIDEBAR_W
HANDLE = 12
MIN_FRAC = 0.02


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent.parent


PROJECT_ROOT = _project_root()
BAR_ROOT = PROJECT_ROOT / "NeuroMods" / "Bar"
IMAGES_DIR = BAR_ROOT / "Bar Images"
CONFIG_PATH = BAR_ROOT / "customer_viewport.json"


def _clamp_viewport(x: float, y: float, w: float, h: float) -> tuple[float, float, float, float]:
    w = max(MIN_FRAC, min(1.0, w))
    h = max(MIN_FRAC, min(1.0, h))
    x = max(0.0, min(1.0 - w, x))
    y = max(0.0, min(1.0 - h, y))
    return x, y, w, h


def _viewport_screen_rect(
    viewport: tuple[float, float, float, float],
) -> pygame.Rect:
    vx, vy, vw, vh = viewport
    return pygame.Rect(
        int(vx * PREVIEW_W),
        int(vy * WIN_H),
        max(8, int(vw * PREVIEW_W)),
        max(8, int(vh * WIN_H)),
    )


def _viewport_from_screen_rect(rect: pygame.Rect) -> tuple[float, float, float, float]:
    return _clamp_viewport(
        rect.x / PREVIEW_W,
        rect.y / WIN_H,
        rect.width / PREVIEW_W,
        rect.height / WIN_H,
    )


def _handle_at(mx: int, my: int, rect: pygame.Rect) -> str | None:
    for name, hx, hy in (
        ("nw", rect.left, rect.top),
        ("ne", rect.right, rect.top),
        ("sw", rect.left, rect.bottom),
        ("se", rect.right, rect.bottom),
        ("n", rect.centerx, rect.top),
        ("s", rect.centerx, rect.bottom),
        ("w", rect.left, rect.centery),
        ("e", rect.right, rect.centery),
    ):
        if abs(mx - hx) <= HANDLE and abs(my - hy) <= HANDLE:
            return name
    return None


def _move_rect(base: pygame.Rect, mx: int, my: int, anchor: tuple[int, int]) -> pygame.Rect:
    ax, ay = anchor
    return base.move(mx - ax, my - ay)


def _resize_from_handle(
    base: pygame.Rect,
    handle: str,
    mx: int,
    my: int,
) -> pygame.Rect:
    left, top, right, bottom = base.left, base.top, base.right, base.bottom
    if "w" in handle:
        left = min(mx, right - 8)
    if "e" in handle:
        right = max(mx, left + 8)
    if "n" in handle:
        top = min(my, bottom - 8)
    if "s" in handle:
        bottom = max(my, top + 8)
    return pygame.Rect(left, top, right - left, bottom - top)


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Customer Portrait Viewport Tool")
    small = pygame.font.SysFont("dejavusans", 14)
    title = pygame.font.SysFont("dejavusans", 20, bold=True)

    frame_surface = load_customer_frame_surface(IMAGES_DIR, pygame)
    roster = AIloadCustomerRoster(BAR_ROOT)
    if not roster:
        print("No customers in customers.txt / Customer Images/")
        pygame.quit()
        sys.exit(1)

    vx, vy, vw, vh, name_gap, name_height = load_customer_viewport(BAR_ROOT)
    viewport = (vx, vy, vw, vh)

    sample_idx = 0
    sample_entry = roster[sample_idx]
    sample_path = AIresolveCustomerImagePath(BAR_ROOT, sample_entry.image_file)
    headshot = pygame.image.load(str(sample_path)).convert_alpha()

    dirty = False
    drag_mode: str | None = None
    drag_anchor = (0, 0)
    drag_base_rect: pygame.Rect | None = None
    drag_start_rect: pygame.Rect | None = None
    editing_field: str | None = None
    edit_text = ""

    running = True
    while running:
        mx, my = pygame.mouse.get_pos()
        in_preview = mx < PREVIEW_W
        vp_rect = _viewport_screen_rect(viewport)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_q and (event.mod & pygame.KMOD_CTRL):
                    running = False
                elif event.key == pygame.K_s:
                    save_customer_viewport(
                        *viewport,
                        BAR_ROOT,
                        name_gap=name_gap,
                        name_height=name_height,
                    )
                    dirty = False
                    print(f"Saved {CONFIG_PATH}")
                elif event.key == pygame.K_r:
                    viewport = DEFAULT_CUSTOMER_VIEWPORT
                    name_gap = DEFAULT_NAME_GAP
                    name_height = DEFAULT_NAME_HEIGHT
                    dirty = True
                elif event.key == pygame.K_LEFTBRACKET:
                    sample_idx = (sample_idx - 1) % len(roster)
                    sample_entry = roster[sample_idx]
                    p = AIresolveCustomerImagePath(BAR_ROOT, sample_entry.image_file)
                    headshot = pygame.image.load(str(p)).convert_alpha()
                elif event.key == pygame.K_RIGHTBRACKET:
                    sample_idx = (sample_idx + 1) % len(roster)
                    sample_entry = roster[sample_idx]
                    p = AIresolveCustomerImagePath(BAR_ROOT, sample_entry.image_file)
                    headshot = pygame.image.load(str(p)).convert_alpha()
                elif editing_field:
                    if event.key == pygame.K_RETURN:
                        try:
                            val = float(edit_text.strip()) if editing_field != "name_gap" else int(edit_text.strip())
                            x, y, w, h = viewport
                            if editing_field == "x":
                                viewport = _clamp_viewport(val, y, w, h)
                            elif editing_field == "y":
                                viewport = _clamp_viewport(x, val, w, h)
                            elif editing_field == "width":
                                viewport = _clamp_viewport(x, y, val, h)
                            elif editing_field == "height":
                                viewport = _clamp_viewport(x, y, w, val)
                            elif editing_field == "name_gap":
                                name_gap = max(0, int(val))
                            dirty = True
                        except ValueError:
                            pass
                        editing_field = None
                        edit_text = ""
                    elif event.key == pygame.K_BACKSPACE:
                        edit_text = edit_text[:-1]
                    elif event.unicode and (
                        event.unicode.isdigit() or event.unicode in ".-"
                    ):
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
                if click_x >= PREVIEW_W:
                    field_boxes = getattr(main, "_field_boxes", {})
                    for name, box in field_boxes.items():
                        if box.collidepoint(click_x, click_y):
                            editing_field = name
                            edit_text = ""
                            break
                elif click_x < PREVIEW_W:
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
            elif event.type == pygame.MOUSEMOTION and drag_mode:
                motion_x, motion_y = event.pos
                if motion_x >= PREVIEW_W:
                    continue
                bounds = pygame.Rect(0, 0, PREVIEW_W, WIN_H)
                if drag_mode == "draw" and drag_start_rect is not None:
                    sx, sy = drag_anchor
                    drag_start_rect = pygame.Rect(
                        min(sx, motion_x), min(sy, motion_y),
                        abs(motion_x - sx), abs(motion_y - sy))
                    viewport = _viewport_from_screen_rect(drag_start_rect)
                    dirty = True
                elif drag_mode == "move" and drag_base_rect is not None:
                    new_rect = _move_rect(drag_base_rect, motion_x, motion_y, drag_anchor)
                    new_rect.clamp_ip(bounds)
                    viewport = _viewport_from_screen_rect(new_rect)
                    dirty = True
                elif drag_base_rect is not None:
                    new_rect = _resize_from_handle(
                        drag_base_rect, drag_mode, motion_x, motion_y)
                    new_rect.clamp_ip(bounds)
                    viewport = _viewport_from_screen_rect(new_rect)
                    dirty = True

        screen.fill((18, 18, 22))
        if frame_surface is not None:
            scaled, fx, fy, _, _ = _scale_to_fit(frame_surface, PREVIEW_W, WIN_H, pygame)
            screen.blit(scaled, (fx, fy))
        else:
            screen.fill((8, 8, 8), (0, 0, PREVIEW_W, WIN_H))

        inner_x, inner_y, inner_w, inner_h = (
            vp_rect.x, vp_rect.y, vp_rect.width, vp_rect.height)
        portrait_scaled, px, py, _, _ = _scale_to_fit(headshot, inner_w, inner_h, pygame)
        screen.blit(portrait_scaled, (inner_x + px, inner_y + py))

        overlay = pygame.Surface((inner_w, inner_h), pygame.SRCALPHA)
        overlay.fill((255, 220, 0, 35))
        screen.blit(overlay, (inner_x, inner_y))
        pygame.draw.rect(screen, (255, 220, 0), vp_rect, 2)

        name_surf = small.render(sample_entry.display_name, True, (255, 235, 70))
        pad_x, pad_y = 10, 4
        bg_w = name_surf.get_width() + 2 * pad_x
        bg_h = name_height
        bg_x = inner_x + (inner_w - bg_w) // 2
        bg_y = inner_y + inner_h + name_gap
        label_bg = pygame.Surface((bg_w, bg_h), pygame.SRCALPHA)
        pygame.draw.rect(label_bg, (0, 0, 0, 178), (0, 0, bg_w, bg_h), border_radius=4)
        screen.blit(label_bg, (bg_x, bg_y))
        screen.blit(
            name_surf,
            (bg_x + (bg_w - name_surf.get_width()) // 2,
             bg_y + (bg_h - name_surf.get_height()) // 2))

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

        pygame.draw.line(screen, (50, 50, 58), (PREVIEW_W, 0), (PREVIEW_W, WIN_H), 2)

        sx = PREVIEW_W + 16
        sy = 16
        screen.blit(title.render("Customer portrait", True, (240, 240, 245)), (sx, sy))
        sy += 32
        lines = [
            "Viewport fractions of game window (0–1).",
            "Drag on preview: new rect",
            "Drag inside: move | handles: resize",
            "Arrows: nudge | Shift+arrows: resize",
            "[ / ] : prev / next customer sample",
            "S save | R reset | Ctrl+Q quit",
            "",
            f"Sample: {sample_entry.display_name}",
            f"Image: {sample_entry.image_file}",
            "",
        ]
        for line in lines:
            screen.blit(small.render(line, True, (170, 170, 180)), (sx, sy))
            sy += 18

        field_boxes: dict[str, pygame.Rect] = {}
        x, y, w, h = viewport
        for label, value, key in (
            ("x", f"{x:.3f}", "x"),
            ("y", f"{y:.3f}", "y"),
            ("width", f"{w:.3f}", "width"),
            ("height", f"{h:.3f}", "height"),
            ("name_gap", str(name_gap), "name_gap"),
        ):
            txt = f"{label}: {value}"
            if editing_field == key:
                txt = f"{label}: {edit_text}|"
            box = pygame.Rect(sx, sy, SIDEBAR_W - 32, 22)
            field_boxes[key] = box
            pygame.draw.rect(screen, (32, 32, 38), box, border_radius=3)
            screen.blit(small.render(txt, True, (220, 220, 230)), (sx + 6, sy + 3))
            sy += 28
        main._field_boxes = field_boxes

        if dirty:
            screen.blit(small.render("Unsaved changes (S to save)", True, (255, 200, 80)), (sx, WIN_H - 28))

        pygame.display.flip()

    pygame.quit()
    if dirty:
        print("Unsaved changes — run again and press S to save.")


if __name__ == "__main__":
    main()