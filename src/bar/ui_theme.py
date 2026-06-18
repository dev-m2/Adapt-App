"""Dark grey + yellow UI palette and draw helpers for the bar trainer."""

from __future__ import annotations

PANEL_RADIUS = 8
BTN_RADIUS = 6

# Core yellow accents (unchanged)
YELLOW = (255, 215, 0)
YELLOW_BRIGHT = (255, 235, 70)
YELLOW_BORDER = (215, 180, 0)
YELLOW_MUTED = (175, 150, 35)

# Very dark grey surfaces (not pure black)
GUI_DARK = (22, 22, 24)
GUI_DARK_DEEP = (18, 18, 20)
GUI_DARK_PANEL = (26, 26, 28)
GUI_DARK_RAISED = (32, 32, 34)

BG_LETTERBOX = GUI_DARK
CUSTOMER_BG = GUI_DARK_DEEP
PANEL_FILL = GUI_DARK_PANEL
PANEL_BORDER = YELLOW_BORDER
PANEL_HEADER = YELLOW_BRIGHT
PANEL_BODY = (245, 245, 238)
PANEL_MUTED = (165, 160, 120)
PANEL_HINT = (125, 120, 85)
PANEL_ACCENT = YELLOW

ACTION_FILL = GUI_DARK_DEEP
ACTION_BORDER = YELLOW_BORDER
ACTION_HOVER = GUI_DARK_RAISED
ACTION_TEXT = YELLOW_BRIGHT

ACCENT_FILL = (28, 24, 6)
ACCENT_HOVER = (42, 36, 0)
ACCENT_BORDER = YELLOW_BRIGHT
ACCENT_TEXT = YELLOW_BRIGHT

OVERLAY_ALPHA = 170
MODAL_FILL = PANEL_FILL
MODAL_BORDER = YELLOW_BORDER

HAND_BADGE_FILL = GUI_DARK_DEEP
HAND_BADGE_BORDER = YELLOW_BORDER

TOOLTIP_FILL = GUI_DARK_DEEP
TOOLTIP_BORDER = YELLOW_BORDER
TOOLTIP_TEXT = YELLOW_BRIGHT

CONSOLE_FILL = GUI_DARK_DEEP
CONSOLE_BORDER = YELLOW_MUTED
CONSOLE_TEXT = (210, 205, 175)

VIEW_LABEL = YELLOW_BRIGHT
HELP_FOOTER = PANEL_MUTED

REPORT_FILL = (28, 28, 24)
REPORT_BORDER = YELLOW_BORDER

# Customer screen overlays on background photo
TRANSLUCENT_PANEL_ALPHA = 128
TRANSLUCENT_BUTTON_ALPHA = 204
HOVER_PANEL_ALPHA_BUMP = 8
HOVER_BUTTON_ALPHA_BUMP = 10
HOVER_PANEL_FILL_SHIFT = 6
HOVER_BUTTON_FILL = GUI_DARK_DEEP
HOVER_GROW_AMOUNT = 0.035
PHOTO_HOVER_GROW_AMOUNT = 0.055
HOVER_GROW_SPEED = 9.0

LOAD_BG = GUI_DARK
LOAD_TITLE_PRACTICE = YELLOW_BRIGHT
LOAD_TITLE_REVIEW = (255, 220, 120)
LOAD_BAR_BG = GUI_DARK_RAISED
LOAD_BAR_FILL = YELLOW
LOAD_BAR_BORDER = YELLOW_BORDER
LOAD_MUTED = PANEL_MUTED


def _shift(rgb: tuple[int, int, int], delta: int) -> tuple[int, int, int]:
    return tuple(max(0, min(255, c + delta)) for c in rgb)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def AIlerpColor(
    color_a: tuple[int, int, int],
    color_b: tuple[int, int, int],
    t: float,
) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return tuple(int(_lerp(a, b, t)) for a, b in zip(color_a, color_b))


def AIscaleRectAroundCenter(
    rect: tuple[int, int, int, int],
    scale: float,
) -> tuple[int, int, int, int]:
    if abs(scale - 1.0) < 0.001:
        return rect
    x, y, w, h = rect
    cx = x + w / 2
    cy = y + h / 2
    nw = max(1, int(w * scale))
    nh = max(1, int(h * scale))
    return int(cx - nw / 2), int(cy - nh / 2), nw, nh


class AIHoverGrow:
    """Smooth 0..1 hover progress keyed by widget id (for size and opacity easing)."""

    def __init__(self) -> None:
        self._progress: dict[str, float] = {}

    def update(self, key: str, hovered: bool, dt_seconds: float) -> float:
        t = self._progress.get(key, 0.0)
        target = 1.0 if hovered else 0.0
        step = HOVER_GROW_SPEED * dt_seconds
        if t < target:
            t = min(target, t + step)
        else:
            t = max(target, t - step)
        self._progress[key] = t
        return t

    def scale(self, hover_t: float, *, photo: bool = False) -> float:
        amount = PHOTO_HOVER_GROW_AMOUNT if photo else HOVER_GROW_AMOUNT
        return 1.0 + hover_t * amount


def point_in_rect(mx: int, my: int, rect: tuple[int, int, int, int]) -> bool:
    return rect[0] <= mx < rect[0] + rect[2] and rect[1] <= my < rect[1] + rect[3]


def draw_panel(
    screen,
    rect: tuple[int, int, int, int],
    *,
    fill: tuple[int, int, int] | None = None,
    border: tuple[int, int, int] | None = None,
    hovered: bool = False,
    hover_blend: float | None = None,
    radius: int = PANEL_RADIUS,
    alpha: int | None = None,
) -> None:
    import pygame

    blend = hover_blend if hover_blend is not None else (1.0 if hovered else 0.0)
    base_fill = fill or PANEL_FILL
    base_border = border or PANEL_BORDER
    if blend > 0:
        base_fill = _shift(base_fill, int(HOVER_PANEL_FILL_SHIFT * blend))
        base_border = _shift(base_border, int(14 * blend))
    if alpha is not None:
        x, y, w, h = rect
        draw_alpha = min(255, alpha + int(HOVER_PANEL_ALPHA_BUMP * blend))
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(surf, (*base_fill, draw_alpha), (0, 0, w, h), border_radius=radius)
        pygame.draw.rect(
            surf, (*base_border, min(255, draw_alpha + 24)), (0, 0, w, h), 2, border_radius=radius)
        screen.blit(surf, (x, y))
        return
    pygame.draw.rect(screen, base_fill, rect, border_radius=radius)
    pygame.draw.rect(screen, base_border, rect, 2, border_radius=radius)


def draw_action_button(
    screen,
    rect: tuple[int, int, int, int],
    label: str,
    font,
    *,
    hovered: bool = False,
    hover_blend: float | None = None,
    accent: bool = False,
    alpha: int | None = None,
) -> None:
    import pygame

    blend = hover_blend if hover_blend is not None else (1.0 if hovered else 0.0)
    if accent and alpha is None:
        fill = AIlerpColor(ACCENT_FILL, ACCENT_HOVER, blend)
        border = ACCENT_BORDER
        text_col = ACCENT_TEXT
    else:
        fill = AIlerpColor(ACTION_FILL, HOVER_BUTTON_FILL, blend)
        border = AIlerpColor(ACTION_BORDER, _shift(YELLOW_BORDER, 12), blend)
        text_col = ACCENT_TEXT if accent else ACTION_TEXT

    if alpha is not None:
        x, y, w, h = rect
        draw_alpha = min(255, alpha + int(HOVER_BUTTON_ALPHA_BUMP * blend))
        btn = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(btn, (*fill, draw_alpha), (0, 0, w, h), border_radius=BTN_RADIUS)
        pygame.draw.rect(
            btn, (*border, min(255, draw_alpha + 20)), (0, 0, w, h), 1, border_radius=BTN_RADIUS)
        screen.blit(btn, (x, y))
    else:
        pygame.draw.rect(screen, fill, rect, border_radius=BTN_RADIUS)
        pygame.draw.rect(screen, border, rect, 1, border_radius=BTN_RADIUS)
    surf = font.render(label, True, text_col)
    bx = rect[0] + (rect[2] - surf.get_width()) // 2
    by = rect[1] + (rect[3] - surf.get_height()) // 2
    screen.blit(surf, (bx, by))


def draw_modal_overlay(screen, win_w: int, win_h: int) -> None:
    import pygame

    overlay = pygame.Surface((win_w, win_h), pygame.SRCALPHA)
    overlay.fill((*GUI_DARK, OVERLAY_ALPHA))
    screen.blit(overlay, (0, 0))


def draw_tooltip(
    screen,
    text: str,
    font,
    mx: int,
    my: int,
    win_w: int,
    win_h: int,
) -> None:
    import pygame

    tip_surf = font.render(text, True, TOOLTIP_TEXT)
    tip_x = mx + 12
    tip_y = my + 8
    if tip_x + tip_surf.get_width() + 4 > win_w:
        tip_x = mx - tip_surf.get_width() - 14
    if tip_y + tip_surf.get_height() + 4 > win_h:
        tip_y = my - tip_surf.get_height() - 14
    bg = pygame.Rect(tip_x - 4, tip_y - 4, tip_surf.get_width() + 8, tip_surf.get_height() + 8)
    pygame.draw.rect(screen, TOOLTIP_FILL, bg, border_radius=4)
    pygame.draw.rect(screen, TOOLTIP_BORDER, bg, 1, border_radius=4)
    screen.blit(tip_surf, (tip_x, tip_y))