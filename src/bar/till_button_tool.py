"""
In-house Till Button Editor (updated for new image folders)

Run with:
    python -m src.bar.till_button_tool

Features:
- Switch between till views and new position views (click sidebar or arrow keys)
- Drag on the image to create a new button box (in original image pixels)
- Click an existing box to select and edit it
- Click color swatches to change color
- Click in the Label or Action fields to edit text (type + Enter or click away)
- Delete selected with DELETE key (or Ctrl+D)
- S to save
- Ctrl+Q to quit (saves automatically on exit; ESC no longer quits)
- The tool automatically saves to NeuroMods/Bar/till_buttons.json when leaving (Ctrl+Q or window close)
- Game automatically loads it
- All till names shown + clickable along the bottom bar

Images loaded from:
- Till screens: NeuroMods/Bar/Till Images/
- Position/spot views (new naming 1N1.jpg etc.): NeuroMods/Bar/Bar Images/
  New images added to Bar Images/ are automatically discovered.

Actions supported in game:
- "order:ItemName" or "order:wordNewThing&Another"  -> adds to orders (note: take: use the required camel& scheme)
- "take:wordNewThing&AnotherThing"  -> take item (all take: buttons must follow this naming)
  (holding shotsGlass/shotGlass + take:spirit → spiritSingle; repeat → spiritDouble)
- "send_order"            -> prints full order and clears
- "switch:tillFoodBurgers" or "switch:tillLager" -> changes to that till screen (till names use camelCase)
- "pour:BASE"             -> pour beer glass in hand (BASE -> BASEHalf -> BASEFull)
- "crafting:RESULT"       -> craft using items in both hands (fixed recipe)
- "craft:" / "craft:combine" -> combine thimble-measured wines/spirits of same base in both hands
- "thimble:25" / "thimble:50" / "thimble:125" -> measure wine or spirit in clicked hand (e.g. vodkaAbsolut -> vodkaAbsolut25)
- "void:" or "void"       -> removes the most recently added order item
- New send grades etc. also supported if defined in json

Colors: cyan, blue, yellow, white, red, purple, grey, orange, light orange, green, etc.
Special: "transparent black" (semi fill + text), "transparent border" (new default: fully transparent + black border, no text).
Add more in the COLORS dict below if needed.
"""

import pygame
import json
from pathlib import Path
import sys
from datetime import datetime

# --- Path setup ---
def _get_project_root():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent.parent

PROJECT_ROOT = _get_project_root()
IMAGES_ROOT = PROJECT_ROOT / "NeuroMods" / "Bar"
BUTTONS_FILE = PROJECT_ROOT / "NeuroMods" / "Bar" / "till_buttons.json"

import re

def normalize_take_suffix(suffix):
    """Normalize a take: suffix to the required scheme: wordNewThing&AnotherThing
    (split on _ / space, camelCase parts, use & for compound separators, first word starts lower).
    Idempotent on already-normalized or mixed inputs.
    """
    if not suffix or not suffix.strip():
        return suffix
    s = suffix.strip()
    s = s.replace('&', ' & ')
    s = re.sub(r'[\s_]+', ' ', s)
    raw_tokens = [t for t in s.split() if t]
    def split_camel(w):
        if w == '&':
            return [w]
        parts = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', w).split()
        return parts
    atomics = []
    for t in raw_tokens:
        atomics.extend(split_camel(t))
    def _join_cased_group(words, make_first_lower):
        cased = []
        for w in words:
            if "'" in w:
                parts = w.split("'")
                cased_w = "'".join((p.capitalize() if p else '') for p in parts)
            else:
                cased_w = w.capitalize()
            cased.append(cased_w)
        joined = ''.join(cased)
        if make_first_lower and joined and joined[0].isalpha():
            joined = joined[0].lower() + joined[1:]
        return joined
    result_parts = []
    current_group = []
    is_very_first = True
    for atom in atomics:
        if atom == '&':
            if current_group:
                joined = _join_cased_group(current_group, is_very_first)
                result_parts.append(joined)
                is_very_first = False
                current_group = []
            result_parts.append('&')
        else:
            current_group.append(atom)
    if current_group:
        joined = _join_cased_group(current_group, is_very_first)
        result_parts.append(joined)
    out = ''.join(result_parts)
    out = out.replace("'S", "'s")
    return out

def normalize_action(action):
    """If action is a take:..., return it with normalized suffix. Otherwise unchanged."""
    if not action:
        return action
    if action.lower().startswith("take:"):
        suf = action[5:]
        return "take:" + normalize_take_suffix(suf)
    return action

# --- Available views ---
# Till views use Till Images/ (keys must match those in game.py VIEWS and till_buttons.json)
# Till names now use camelCase (consistent with take: naming scheme).
# Dynamically discover so new camelCase images are automatically supported.
TILL_VIEW_MAP = {}
till_dir = IMAGES_ROOT / "Till Images"
if till_dir.exists():
    for img_file in sorted(till_dir.glob("*.jpg")):
        stem = img_file.stem
        if stem.startswith("till"):
            TILL_VIEW_MAP[stem] = f"Till Images/{img_file.name}"

# Position views (Bar Images/ with new SpotDirectionHeight naming)
# Dynamically discover so new images are automatically supported
POSITION_VIEW_MAP = {}
bar_dir = IMAGES_ROOT / "Bar Images"
if bar_dir.exists():
    for img_file in sorted(bar_dir.glob("*.jpg")):
        stem = img_file.stem
        # e.g. 1E1, 7S0 etc.
        if len(stem) == 3 and stem[0].isdigit() and stem[1] in "NSEW" and stem[2].isdigit():
            POSITION_VIEW_MAP[stem] = f"Bar Images/{img_file.name}"

VIEW_MAP = {**TILL_VIEW_MAP, **POSITION_VIEW_MAP}

# Navigation order for left/right arrows
# Till screens left of home, then home, then position views (new spots from Bar Images) on the right.
TILL_SCREENS_LEFT = [
    "tillFood",
    "tillFoodBreakfast",
    "tillFoodDaytime",
    "tillFoodBurgers",
    "tillFoodCarvery",
    "tillFoodDesserts",
    "tillFoodKids",
    "tillFoodMealdeal",
    "tillFoodSides",
    "tillDrinks",
    "tillDrinksLager",
    "tillDrinksBitter",
    "tillDrinksSpirits",
    "tillDrinksWineRed125",
    "tillDrinksWineWhite125",
    "tillDrinksWineRose125",
    "tillDrinksBottlesLager",
    "tillDrinksBottlesCider",
    "tillDrinksBottlesAle",
    "tillDrinksSofts",
    "tillDrinksKids",
    "tillDrinksCrisps",
]
HOME_TILL = "tillDrinks"

# Ordered list of all till names for the bottom bar in the editor (click to switch view).
# All till names listed along the bottom (camelCase names). Dynamically includes all discovered till* views.
TILL_BOTTOM_LIST = [HOME_TILL] + sorted([k for k in TILL_VIEW_MAP if k.startswith("till") and k != HOME_TILL])

# Position views on the right: dynamically from discovered ones, sorted by spot then direction/height
def _sort_key(k):
    if len(k) == 3 and k[0].isdigit():
        spot = int(k[0])
        dir_char = k[1]
        h = int(k[2])
        # Prefer order: N, S, E, W or something logical
        dir_order = {"N": 0, "S": 1, "E": 2, "W": 3}.get(dir_char, 99)
        return (spot, dir_order, h)
    return (99, 99, 99)

POSITION_VIEWS_RIGHT = sorted(POSITION_VIEW_MAP.keys(), key=_sort_key)
VIEWS_ORDER = TILL_SCREENS_LEFT + [HOME_TILL] + POSITION_VIEWS_RIGHT

# Color palette (add more names if you want)
COLORS = {
    "cyan": (0, 255, 255),
    "blue": (30, 144, 255),
    "yellow": (255, 255, 0),
    "white": (255, 255, 255),
    "red": (220, 20, 60),
    "purple": (148, 0, 211),
    "grey": (128, 128, 128),
    "orange": (255, 140, 0),
    "light orange": (255, 200, 100),
    "green": (50, 205, 50),
    "dark blue": (0, 0, 139),
    "pink": (255, 105, 180),
    "brown": (139, 69, 19),
    "transparent black": (0, 0, 0),
    "transparent border": (0, 0, 0),  # completely transparent fill + opaque black border only; no text drawn
}

def load_buttons():
    if BUTTONS_FILE.exists():
        with open(BUTTONS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_buttons(data):
    BUTTONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(BUTTONS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Saved to {BUTTONS_FILE} at {ts}")

def load_image(view):
    path = IMAGES_ROOT / VIEW_MAP[view]
    if not path.exists():
        print(f"Warning: Image not found {path}")
        return None
    return pygame.image.load(str(path)).convert()

def main():
    pygame.init()
    screen = pygame.display.set_mode((1280, 800), pygame.RESIZABLE)
    pygame.display.set_caption("Till Button Editor - Drag to draw, click to edit | F11: fullscreen")
    clock = pygame.time.Clock()
    from .ui_fonts import ui_font

    font = ui_font(24)
    small_font = ui_font(20)

    def _wrap_text(text, font, max_width):
        """Word-wrap text to fit within max_width pixels using the given font."""
        if not text:
            return [""]
        words = text.split()
        lines = []
        current_line = []
        for word in words:
            test_line = ' '.join(current_line + [word])
            if font.size(test_line)[0] <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
        if current_line:
            lines.append(' '.join(current_line))
        return lines

    button_data = load_buttons()  # { "tillDrinks": [ {"rect": [...], "label":.., "color":.., "action":..}, ... ], ... }

    view_keys = VIEWS_ORDER  # ordered for arrow navigation
    current_view = "tillDrinks"
    current_img = load_image(current_view)

    selected_idx = None
    drawing = False
    drag_start = None

    # Simple text editing
    editing_label = False
    editing_action = False
    label_text = ""
    action_text = ""
    sugg_selected = 0
    is_fullscreen = False

    running = True
    while running:
        screen.fill((40, 40, 45))

        win_w, win_h = screen.get_size()

        # Dynamic layout for resizable / fullscreen
        # Left margin for instructions, image expands to fill, but we cap the right edge of the image area
        # so that the right-aligned "Current: " label + some margin stays clearly left of the top-right palette/editing UI.
        left_margin = 280  # reserve enough left space so the (wrapped) instructions are not cramped against or visually hidden by the main image area
        left_text_x = 10
        img_x = left_margin
        right_ui_width = 250  # tight to the actual drawn content width of the right column so that after the colours+their labels there is only a tiny margin on the far right (addresses the "empty space" complaint)
        panel_x = win_w - right_ui_width
        gap = 60  # horizontal separation between image right edge and palette start (prevents image from overlapping the top-right colours+text)
        available = max(0, panel_x - img_x - gap)
        img_w = max(400, min(1200, available))  # never let image area eat into the right UI column
        img_y = 30
        img_h = max(400, win_h - 180)
        IMG_AREA = (img_x, img_y, img_w, img_h)

        mx, my = pygame.mouse.get_pos()
        hovered_action = None
        button_list_rects = []  # for selecting off-screen buttons via list
        button_screen_rects = []  # screen-space rects for all buttons (including off-image-area ones) for click selection

        # Compute action autocomplete suggestions based on previous actions in button_data
        # Enhanced: cross-suggest between take:/order: (shared suffixes) + full support for switch:
        # E.g. if take:madriGlass exists, "order:ma" suggests "order:madriGlass"
        # "switch:til" or "switch:1n" or "sw:food" will suggest matching "switch:tillFoodBurgers" / "switch:1N1" etc.
        # Uses known views from VIEW_MAP so suggestions work even before any switch: buttons are created.
        current_suggestions = []
        if editing_action and selected_idx is not None and current_view in button_data:
            all_actions = set()
            for vbtns in button_data.values():
                for b in vbtns:
                    a = str(b.get("action", "")).strip()
                    if a:
                        all_actions.add(a)
            # Build suffix pools for cross-prefix support (take/order as before)
            take_suffixes = {a[5:] for a in all_actions if a.lower().startswith("take:") and a[5:].strip()}
            order_suffixes = {a[6:] for a in all_actions if a.lower().startswith("order:") and a[6:].strip()}
            all_suffixes = take_suffixes | order_suffixes

            # Authoritative list of switch: targets (all known views: tills in camelCase + positions like 1N1 + customer)
            switch_targets = set(VIEW_MAP.keys())

            curr = action_text.lower().strip()
            direct = []
            cross = []
            if curr:
                direct = [a for a in all_actions if curr in a.lower()]
                lower_curr = curr
                # Cross for switch: (always available from VIEW_MAP, even with no existing switch buttons)
                if lower_curr.startswith("switch") or lower_curr.startswith("sw"):
                    if ":" in lower_curr:
                        partial = lower_curr.split(":", 1)[1]
                    elif lower_curr.startswith("switch"):
                        partial = lower_curr[6:]
                    else:
                        partial = lower_curr[2:] if len(lower_curr) > 2 else ""
                    for target in sorted(switch_targets):
                        if (not partial) or (partial in target.lower()):
                            cross.append("switch:" + target)
                # Cross: synthesize order:xxx from take suffixes (and vice-versa) when partial matches suffix
                if lower_curr.startswith("order:") or lower_curr.startswith("order"):
                    partial = lower_curr.split(":", 1)[1] if ":" in lower_curr else (lower_curr[5:] if lower_curr.startswith("order") else lower_curr)
                    for suf in sorted(all_suffixes):
                        if (not partial) or (partial in suf.lower()):
                            cross.append("order:" + suf)
                if lower_curr.startswith("take:") or lower_curr.startswith("take"):
                    partial = lower_curr.split(":", 1)[1] if ":" in lower_curr else (lower_curr[4:] if lower_curr.startswith("take") else lower_curr)
                    for suf in sorted(all_suffixes):
                        if (not partial) or (partial in suf.lower()):
                            cross.append("take:" + suf)
                # Support for void: (deletes most recent order item) - suggest even if no such button exists yet
                if "void" in lower_curr or lower_curr.startswith("v"):
                    cross.append("void:")
                # Support for thimble: wine measures - suggest the three standard sizes
                if "thimble" in lower_curr or lower_curr.startswith("thi") or lower_curr.startswith("th"):
                    for tsize in ("25", "50", "125"):
                        cross.append("thimble:" + tsize)
                if "opener" in lower_curr or lower_curr.startswith("op"):
                    cross.append("opener:")
            else:
                direct = sorted(all_actions)

            # Merge direct first (existing full actions), then cross (synthesized), dedup, limit
            seen = set()
            suggestions = []
            for s in direct + cross:
                if s not in seen:
                    seen.add(s)
                    suggestions.append(s)
            current_suggestions = suggestions[:8]

            # Clamp selection when suggestions change
            if current_suggestions:
                sugg_selected = min(sugg_selected, len(current_suggestions) - 1)
            else:
                sugg_selected = 0

        # Instructions (no sidebar list) — left margin, line-wrapped so they don't get hidden by the image area
        inst = [
            "Left/Right arrows: switch view",
            "Scroll wheel up/down: prev/next view (or suggestion list when editing Action)",
            "Bottom list: click any till name to switch view",
            "Ctrl+click a switch: button: jump to that screen (instead of select)",
            "Drag on image: create new button (now defaults to blank label + order:)",
            "Click existing box: select (or use list below / Ctrl+PgUp/Dn for off-screen)",
            "DEL: delete selected",
            "Click color swatches to change color",
            "Click Label/Action boxes to type (Enter to finish)",
            "Editing Action: Up/Down = navigate suggestions, Tab/Enter = accept",
            "Hover button: see action | F11: toggle fullscreen",
            "S: Save   Ctrl+Q: Quit"
        ]
        y = 30
        max_inst_width = left_margin - 30  # wrap to fit comfortably in the reserved left margin, with breathing room before the image
        for line in inst:
            wrapped = _wrap_text(line, small_font, max_inst_width)
            for wline in wrapped:
                txt = small_font.render(wline, True, (180, 180, 180))
                screen.blit(txt, (left_text_x, y))
                y += 16  # slightly tighter line height for wrapped text
            y += 4  # small gap between original instruction items

        # List of buttons in current view (click to select even off-screen ones). Capped to avoid overlap.
        if current_view in button_data:
            bl = button_data[current_view]
            if bl:
                max_list = 6
                screen.blit(small_font.render(f"Buttons in view ({len(bl)}) - click to select (off-screen ok); Ctrl+PgUp/Dn to cycle:", True, (200, 210, 180)), (left_text_x, y))
                y += 16
                for i, b in enumerate(bl[:max_list]):
                    is_sel = (i == selected_idx)
                    col = (255, 255, 100) if is_sel else (160, 160, 170)
                    lab = (b.get("label", "") or "?")[:10]
                    act = (b.get("action", "") or "")[:18]
                    t = f"  {i}: {lab} | {act}"
                    screen.blit(small_font.render(t, True, col), (left_text_x, y))
                    button_list_rects.append((y, y + 14, i))
                    y += 14
                if len(bl) > max_list:
                    screen.blit(small_font.render(f"  ... +{len(bl)-max_list} more (use Ctrl+Up/Down or list click)", True, (140,140,150)), (left_text_x, y))
                    y += 14
                y += 4

        # --- Draw current image (scaled to fit IMG_AREA) ---
        if current_img:
            avail_w, avail_h = IMG_AREA[2], IMG_AREA[3]
            scale = min(avail_w / current_img.get_width(), avail_h / current_img.get_height())
            disp_w = int(current_img.get_width() * scale)
            disp_h = int(current_img.get_height() * scale)
            scaled_img = pygame.transform.smoothscale(current_img, (disp_w, disp_h))

            off_x = IMG_AREA[0] + (avail_w - disp_w) // 2
            off_y = IMG_AREA[1] + (avail_h - disp_h) // 2

            screen.blit(scaled_img, (off_x, off_y))

            # Store for hit testing / drawing
            img_info = {
                "off_x": off_x, "off_y": off_y,
                "scale": scale,
                "disp_w": disp_w, "disp_h": disp_h,
                "orig_w": current_img.get_width(),
                "orig_h": current_img.get_height(),
            }
        else:
            img_info = None

        # --- Draw existing buttons for this view ---
        view_btns = button_data.get(current_view, [])
        if img_info and view_btns:
            for i, btn in enumerate(view_btns):
                rx, ry, rw, rh = btn["rect"]
                sx = img_info["off_x"] + int(rx * img_info["scale"])
                sy = img_info["off_y"] + int(ry * img_info["scale"])
                sw = max(2, int(rw * img_info["scale"]))
                sh = max(2, int(rh * img_info["scale"]))

                button_screen_rects.append((sx, sy, sw, sh, i))

                # Hover detection for tooltip and cursor
                if sx <= mx <= sx + sw and sy <= my <= sy + sh:
                    hovered_action = btn.get("action", "")

                color_name = btn.get("color", "transparent border")
                color = COLORS.get(color_name, (30, 144, 255))

                # Very slightly rounded corners for all till buttons (subtle on the photos)
                radius = max(2, min(6, sw // 2, sh // 2))

                if color_name == "transparent border":
                    # Completely transparent (no fill) + greyish / somewhat opaque black border.
                    # No text/label visible for this variant (pure clickable hotspot).
                    border_surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
                    # Soft dark grey + alpha instead of pure solid black
                    pygame.draw.rect(border_surf, (70, 70, 75, 190), (0, 0, sw, sh), width=2, border_radius=radius)
                    screen.blit(border_surf, (sx, sy))
                    text_col = None  # no text for this variant
                elif color_name == "transparent black":
                    s = pygame.Surface((sw, sh), pygame.SRCALPHA)
                    pygame.draw.rect(s, (0, 0, 0, 128), (0, 0, sw, sh), border_radius=radius)
                    screen.blit(s, (sx, sy))
                    text_col = (255, 255, 255)
                else:
                    pygame.draw.rect(screen, color, (sx, sy, sw, sh), border_radius=radius)  # fill with button color
                    text_col = (0, 0, 0) if color_name != "black" else (255, 255, 255)

                if i == selected_idx:
                    pygame.draw.rect(screen, (255, 255, 0), (sx-2, sy-2, sw+4, sh+4), 2, border_radius=radius+1)

                # Centered text (skip entirely for "transparent border" so no text is visible)
                if text_col is not None:
                    lbl = small_font.render(btn.get("label", "?")[:20], True, text_col)
                    text_x = sx + (sw - lbl.get_width()) // 2
                    text_y = sy + (sh - lbl.get_height()) // 2
                    screen.blit(lbl, (text_x, text_y))

        # --- Tooltip for hovered button action ---
        if hovered_action:
            tip = f"Action: {hovered_action}"
            tip_surf = small_font.render(tip, True, (255, 255, 255))
            tip_x = mx + 12
            tip_y = my + 8
            bg = pygame.Rect(tip_x - 3, tip_y - 3, tip_surf.get_width() + 6, tip_surf.get_height() + 6)
            pygame.draw.rect(screen, (25, 25, 30), bg)
            pygame.draw.rect(screen, (90, 90, 100), bg, 1)
            screen.blit(tip_surf, (tip_x, tip_y))

        # --- Draw color palette (right side) ---
        palette_x = panel_x
        palette_y = 50
        swatch_size = 28
        col = 0
        row = 0
        for name, rgb in COLORS.items():
            x = palette_x + (col * (swatch_size + 4))
            y = palette_y + (row * (swatch_size + 4))
            if name == "transparent border":
                # Preview: dark fill + soft greyish/semi-opaque rounded border
                pygame.draw.rect(screen, (40, 40, 45), (x, y, swatch_size, swatch_size), border_radius=3)
                border_s = pygame.Surface((swatch_size, swatch_size), pygame.SRCALPHA)
                pygame.draw.rect(border_s, (70, 70, 75, 210), (0, 0, swatch_size, swatch_size), width=2, border_radius=3)
                screen.blit(border_s, (x, y))
            elif name == "transparent black":
                s = pygame.Surface((swatch_size, swatch_size), pygame.SRCALPHA)
                pygame.draw.rect(s, (0, 0, 0, 128), (0, 0, swatch_size, swatch_size), border_radius=3)
                screen.blit(s, (x, y))
                pygame.draw.rect(screen, (200, 200, 200), (x, y, swatch_size, swatch_size), 1, border_radius=3)
            else:
                pygame.draw.rect(screen, rgb, (x, y, swatch_size, swatch_size), border_radius=3)
                pygame.draw.rect(screen, (200,200,200), (x, y, swatch_size, swatch_size), 1, border_radius=3)

            col += 1
            if col > 2:
                col = 0
                row += 1

        # --- Editing panel (when something selected) ---
        if selected_idx is not None and selected_idx < len(view_btns):
            btn = view_btns[selected_idx]
            # Use the dynamic panel_x (and the fixed panel_y) from the layout.
            # The previous override "panel_x = max(1120, win_w - 160)" was causing the color swatch *drawing*
            # (which happened earlier using the good layout panel_x) to be out of sync with the *click* calculation
            # (which ran later in the event handler and saw the overridden value).
            panel_y = 320

            # Color label
            screen.blit(font.render("Color:", True, (255,255,255)), (panel_x, panel_y))

            # Current color swatch
            color_name = btn.get("color", "transparent border")
            cur_color = COLORS.get(color_name, (100,100,100))
            if color_name == "transparent border":
                # Show preview of fully transparent + soft greyish rounded border
                pygame.draw.rect(screen, (40, 40, 45), (panel_x + 70, panel_y, 40, 25), border_radius=3)
                bs = pygame.Surface((40, 25), pygame.SRCALPHA)
                pygame.draw.rect(bs, (70, 70, 75, 210), (0, 0, 40, 25), width=2, border_radius=3)
                screen.blit(bs, (panel_x + 70, panel_y))
            else:
                pygame.draw.rect(screen, cur_color, (panel_x + 70, panel_y, 40, 25), border_radius=3)
            screen.blit(small_font.render(color_name, True, (200,200,200)), (panel_x + 115, panel_y + 3))

            # Label field
            screen.blit(font.render("Label:", True, (255,255,255)), (panel_x, panel_y + 40))
            label_box = (panel_x, panel_y + 65, 140, 24)
            pygame.draw.rect(screen, (60,60,60), label_box)
            pygame.draw.rect(screen, (180,180,180), label_box, 1)
            lbl = small_font.render(label_text if editing_label else btn.get("label", ""), True, (255,255,255))
            screen.blit(lbl, (label_box[0] + 5, label_box[1] + 4))

            # Action field
            screen.blit(font.render("Action:", True, (255,255,255)), (panel_x, panel_y + 100))
            action_box = (panel_x, panel_y + 125, 140, 24)
            pygame.draw.rect(screen, (60,60,60), action_box)
            pygame.draw.rect(screen, (180,180,180), action_box, 1)
            act = small_font.render(action_text if editing_action else btn.get("action", ""), True, (255,255,255))
            screen.blit(act, (action_box[0] + 5, action_box[1] + 4))

            # Draw autocomplete suggestions for action field
            if editing_action and current_suggestions:
                sug_y = panel_y + 150
                sug_h = len(current_suggestions) * 16 + 6
                pygame.draw.rect(screen, (45, 45, 50), (panel_x, sug_y, 220, sug_h))
                pygame.draw.rect(screen, (120, 120, 130), (panel_x, sug_y, 220, sug_h), 1)
                for ii, sug in enumerate(current_suggestions):
                    col = (255, 255, 120) if ii == sugg_selected else (210, 210, 210)
                    stxt = small_font.render(sug[:32], True, col)
                    screen.blit(stxt, (panel_x + 4, sug_y + 3 + ii * 16))

            help_lines = [
                "Examples:",
                "take:guinessGlass",
                "take:fruitShootApple&Blackberry",
                "order:Madri",
                "switch:tillFoodBurgers",
                "void:",
                "opener:",
                "send_order"
            ]
            hy = panel_y + 300
            for h in help_lines:
                screen.blit(small_font.render(h, True, (150,150,150)), (panel_x, hy))
                hy += 16

        # --- Current view label (top of the image area, left side) ---
        screen.blit(font.render(f"Current: {current_view}", True, (255,255,100)), (IMG_AREA[0], 5))

        # --- Event handling ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                save_buttons(button_data)
                running = False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                    save_buttons(button_data)
                    running = False
                if event.key == pygame.K_F11:
                    is_fullscreen = not is_fullscreen
                    if is_fullscreen:
                        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                    else:
                        screen = pygame.display.set_mode((1280, 800), pygame.RESIZABLE)
                if event.key == pygame.K_s:
                    save_buttons(button_data)
                if selected_idx is not None and current_view in button_data:
                    if event.key == pygame.K_DELETE or (event.key == pygame.K_d and (pygame.key.get_mods() & pygame.KMOD_CTRL)):
                        del button_data[current_view][selected_idx]
                        selected_idx = None
                        editing_label = editing_action = False
                        sugg_selected = 0

                # Text input
                if editing_label or editing_action:
                    # Suggestion keyboard controls (UP/DOWN to navigate, TAB/RETURN to accept)
                    if editing_action and current_suggestions:
                        if event.key == pygame.K_UP:
                            sugg_selected = max(0, sugg_selected - 1)
                            continue  # consume key, don't do other actions
                        elif event.key == pygame.K_DOWN:
                            sugg_selected = min(len(current_suggestions) - 1, sugg_selected + 1)
                            continue
                        elif event.key in (pygame.K_TAB, pygame.K_RETURN):
                            if 0 <= sugg_selected < len(current_suggestions):
                                sug = current_suggestions[sugg_selected]
                                sug = normalize_action(sug)
                                if selected_idx is not None and current_view in button_data:
                                    btn = button_data[current_view][selected_idx]
                                    btn["action"] = sug
                                action_text = sug
                                editing_action = False
                                sugg_selected = 0
                            continue  # accepted suggestion, skip normal commit + view nav

                    if event.key == pygame.K_RETURN:
                        if selected_idx is not None and current_view in button_data:
                            btn = button_data[current_view][selected_idx]
                            if editing_label:
                                btn["label"] = label_text
                            if editing_action:
                                btn["action"] = normalize_action(action_text)
                        editing_label = editing_action = False
                        sugg_selected = 0
                    elif event.key == pygame.K_BACKSPACE:
                        mods = pygame.key.get_mods()
                        if mods & pygame.KMOD_CTRL:
                            if editing_label:
                                label_text = ""
                            elif editing_action:
                                action_text = ""
                        else:
                            if editing_label:
                                label_text = label_text[:-1]
                            elif editing_action:
                                action_text = action_text[:-1]
                    else:
                        ch = event.unicode
                        if ch:
                            if editing_label:
                                label_text += ch
                            elif editing_action:
                                action_text += ch
                                sugg_selected = 0  # reset suggestion selection on new input

                # Arrow navigation: left = previous in order (till left of home, positions right of home)
                if event.key == pygame.K_LEFT:
                    try:
                        idx = view_keys.index(current_view)
                        new_idx = (idx - 1) % len(view_keys)
                        current_view = view_keys[new_idx]
                        current_img = load_image(current_view)
                        selected_idx = None
                        editing_label = editing_action = False
                        sugg_selected = 0
                    except ValueError:
                        pass
                if event.key == pygame.K_RIGHT:
                    try:
                        idx = view_keys.index(current_view)
                        new_idx = (idx + 1) % len(view_keys)
                        current_view = view_keys[new_idx]
                        current_img = load_image(current_view)
                        selected_idx = None
                        editing_label = editing_action = False
                        sugg_selected = 0
                    except ValueError:
                        pass

                # Cycle selection through all buttons with Ctrl+Up/Down or PageUp/Down (allows selecting off-screen ones)
                if current_view in button_data:
                    n = len(button_data[current_view])
                    if n > 0 and selected_idx is not None:
                        if event.key in (pygame.K_PAGEUP, pygame.K_UP) and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                            selected_idx = (selected_idx - 1) % n
                            editing_label = editing_action = False
                            sugg_selected = 0
                        elif event.key in (pygame.K_PAGEDOWN, pygame.K_DOWN) and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                            selected_idx = (selected_idx + 1) % n
                            editing_label = editing_action = False
                            sugg_selected = 0

            elif event.type == pygame.MOUSEWHEEL:
                # Scroll up = arrow up, scroll down = arrow down.
                if event.y > 0:
                    if editing_action and current_suggestions:
                        sugg_selected = max(0, sugg_selected - 1)
                    else:
                        try:
                            idx = view_keys.index(current_view)
                            current_view = view_keys[(idx - 1) % len(view_keys)]
                            current_img = load_image(current_view)
                            selected_idx = None
                            editing_label = editing_action = False
                            sugg_selected = 0
                        except ValueError:
                            pass
                elif event.y < 0:
                    if editing_action and current_suggestions:
                        sugg_selected = min(len(current_suggestions) - 1, sugg_selected + 1)
                    else:
                        try:
                            idx = view_keys.index(current_view)
                            current_view = view_keys[(idx + 1) % len(view_keys)]
                            current_img = load_image(current_view)
                            selected_idx = None
                            editing_label = editing_action = False
                            sugg_selected = 0
                        except ValueError:
                            pass

            if event.type == pygame.MOUSEBUTTONDOWN and current_img:
                mx, my = event.pos

                # Screen-space hit test for buttons (catches ones whose scaled rect is outside the IMG_AREA / "off-screen")
                # This is why you could hover (see action) but click did nothing before.
                for bsx, bsy, bsw, bsh, idx in button_screen_rects:
                    if bsx <= mx <= bsx + bsw and bsy <= my <= bsy + bsh:
                        selected_idx = idx
                        editing_label = editing_action = False
                        break

                # Click the text list below instructions (alternative way to reach any button)
                for ly1, ly2, bidx in button_list_rects:
                    if left_text_x <= mx <= left_text_x + 260 and ly1 <= my <= ly2:
                        selected_idx = bidx
                        editing_label = editing_action = False
                        sugg_selected = 0
                        break

                # Till names bottom bar (click to switch to that till view)
                till_bar_y = win_h - 22
                till_x = left_text_x
                for tname in TILL_BOTTOM_LIST:
                    tw = small_font.size(tname)[0] + 8
                    if till_x - 4 <= mx <= till_x - 4 + tw and till_bar_y - 3 <= my <= till_bar_y + 15:
                        if tname in VIEW_MAP:
                            current_view = tname
                            current_img = load_image(current_view)
                            selected_idx = None
                            editing_label = editing_action = False
                            sugg_selected = 0
                        break
                    till_x += small_font.size(tname)[0] + 14

                # Autocomplete: click a suggestion to accept it (check BEFORE auto-save)
                if editing_action and current_suggestions and selected_idx is not None and current_view in button_data:
                    panel_y = 320
                    sug_y = panel_y + 150
                    for ii, sug in enumerate(current_suggestions):
                        if panel_x <= mx <= panel_x + 220 and sug_y + ii * 16 <= my <= sug_y + (ii + 1) * 16:
                            sug = normalize_action(sug)
                            btn = button_data[current_view][selected_idx]
                            btn["action"] = sug
                            action_text = sug
                            editing_action = False
                            break

                # Auto-save label/action if editing and click anywhere (including off the fields)
                # This ensures edits are committed on click-off without needing Enter
                if editing_label or editing_action:
                    if selected_idx is not None and current_view in button_data:
                        btn = button_data[current_view][selected_idx]
                        if editing_label:
                            btn["label"] = label_text
                        if editing_action:
                            btn["action"] = normalize_action(action_text)
                    editing_label = editing_action = False
                    sugg_selected = 0

                # Check click on color swatches
                # Now uses the exact same dynamic panel_x that was used to draw the palette this frame
                if selected_idx is not None and current_view in button_data:
                    palette_x = panel_x
                    palette_y = 50
                    sw = 28
                    col = row = 0
                    for name in COLORS:
                        x = palette_x + col * (sw + 4)
                        y = palette_y + row * (sw + 4)
                        if x <= mx <= x+sw and y <= my <= y+sw:
                            button_data[current_view][selected_idx]["color"] = name
                            break
                        col += 1
                        if col > 2:
                            col = 0
                            row += 1

                # Check click on input fields
                if selected_idx is not None:
                    panel_y = 320
                    if  panel_y + 65 <= my <= panel_y + 89 and panel_x <= mx <= panel_x + 140:
                        editing_label = True
                        editing_action = False
                        label_text = button_data[current_view][selected_idx].get("label", "")
                    elif panel_y + 125 <= my <= panel_y + 149 and panel_x <= mx <= panel_x + 140:
                        editing_action = True
                        editing_label = False
                        action_text = button_data[current_view][selected_idx].get("action", "")
                        sugg_selected = 0

                # Image area clicks / drags
                ix, iy = IMG_AREA[0], IMG_AREA[1]
                iw, ih = IMG_AREA[2], IMG_AREA[3]
                if ix <= mx <= ix + iw and iy <= my <= iy + ih:
                    # Convert mouse to original image coordinates
                    scaled, off, sc = get_display_image_for_editor(current_img, IMG_AREA[2], IMG_AREA[3])
                    img_sx = ix + off[0]
                    img_sy = iy + off[1]

                    if img_sx <= mx <= img_sx + scaled.get_width() and img_sy <= my <= img_sy + scaled.get_height():
                        orig_x = int((mx - img_sx) / sc)
                        orig_y = int((my - img_sy) / sc)

                        # Check if clicked existing button
                        view_btns = button_data.get(current_view, [])
                        hit = False
                        for i, b in enumerate(view_btns):
                            bx, by, bw, bh = b["rect"]
                            if bx <= orig_x < bx + bw and by <= orig_y < by + bh:
                                action = str(b.get("action", "")).strip()
                                if event.button == 1 and (pygame.key.get_mods() & pygame.KMOD_CTRL) and action.startswith("switch:"):
                                    # Ctrl+click on switch: button -> navigate to the target view instead of selecting
                                    target = action.split(":", 1)[1].strip() if ":" in action else ""
                                    if target and target in VIEW_MAP:
                                        current_view = target
                                        current_img = load_image(current_view)
                                        selected_idx = None
                                        editing_label = editing_action = False
                                        sugg_selected = 0
                                    hit = True
                                    break
                                else:
                                    selected_idx = i
                                    editing_label = False
                                    editing_action = False
                                    hit = True
                                    break

                        if not hit and event.button == 1:
                            # Start new drag
                            drawing = True
                            drag_start = (orig_x, orig_y)
                            selected_idx = None

            if event.type == pygame.MOUSEBUTTONUP and drawing:
                drawing = False
                if drag_start and current_img:
                    mx, my = event.pos
                    # convert end point
                    scaled, off, sc = get_display_image_for_editor(current_img, IMG_AREA[2], IMG_AREA[3])
                    img_sx = IMG_AREA[0] + off[0]
                    img_sy = IMG_AREA[1] + off[1]
                    orig_x2 = int((mx - img_sx) / sc)
                    orig_y2 = int((my - img_sy) / sc)

                    x1, y1 = drag_start
                    x = min(x1, orig_x2)
                    y = min(y1, orig_y2)
                    w = abs(x1 - orig_x2)
                    h = abs(y1 - orig_y2)

                    if w > 15 and h > 15:
                        new_btn = {
                            "rect": [x, y, w, h],
                            "label": "",
                            "color": "transparent border",
                            "action": "order:"
                        }
                        if current_view not in button_data:
                            button_data[current_view] = []
                        button_data[current_view].append(new_btn)
                        selected_idx = len(button_data[current_view]) - 1
                        editing_label = False
                        editing_action = False
                        label_text = new_btn["label"]
                        action_text = new_btn["action"]

                drag_start = None

        # --- Live drag preview ---
        if drawing and drag_start and current_img:
            mx, my = pygame.mouse.get_pos()
            scaled, off, sc = get_display_image_for_editor(current_img, IMG_AREA[2], IMG_AREA[3])
            img_sx = IMG_AREA[0] + off[0]
            img_sy = IMG_AREA[1] + off[1]
            ox = int((mx - img_sx) / sc)
            oy = int((my - img_sy) / sc)

            x1, y1 = drag_start
            rx = min(x1, ox)
            ry = min(y1, oy)
            rw = abs(x1 - ox)
            rh = abs(y1 - oy)

            sx = IMG_AREA[0] + off[0] + int(rx * sc)
            sy = IMG_AREA[1] + off[1] + int(ry * sc)
            sw = int(rw * sc)
            sh = int(rh * sc)
            rad = max(2, min(6, sw // 2, sh // 2))
            pygame.draw.rect(screen, (255, 255, 0), (sx, sy, sw, sh), 2, border_radius=rad)

        # --- Draw current selected info ---
        info_y = win_h - 80  # dynamic for resizable/fullscreen (leave room for till names bar)
        if selected_idx is not None and current_view in button_data and selected_idx < len(button_data[current_view]):
            btn = button_data[current_view][selected_idx]
            screen.blit(font.render(f"Selected: {btn['label']}", True, (255,255,0)), (left_text_x, info_y))
            screen.blit(small_font.render(f"Action: {btn['action']}", True, (200,200,200)), (left_text_x, info_y + 22))
            screen.blit(small_font.render(f"Color: {btn.get('color','transparent border')}", True, (200,200,200)), (left_text_x, info_y + 40))

        # If hovering a button, show its action in the info area too
        if hovered_action:
            offset = 60 if selected_idx is not None and current_view in button_data and selected_idx < len(button_data[current_view]) else 0
            screen.blit(small_font.render(f"Hovered Action: {hovered_action}", True, (200, 200, 100)), (left_text_x, info_y + offset))

        # --- Till names listed along the bottom (clickable to switch views) ---
        # All till names in camelCase, as requested. Current one highlighted.
        till_bar_y = win_h - 22
        till_x = left_text_x
        till_font = small_font  # reuse; could use even smaller if crowded
        for tname in TILL_BOTTOM_LIST:
            is_cur = (tname == current_view)
            tcol = (255, 255, 120) if is_cur else (170, 170, 180)
            if is_cur:
                tw = till_font.size(tname)[0] + 8
                pygame.draw.rect(screen, (50, 55, 65), (till_x - 4, till_bar_y - 3, tw, 18))
            tlabel = till_font.render(tname, True, tcol)
            screen.blit(tlabel, (till_x, till_bar_y))
            till_x += tlabel.get_width() + 14

        # Set mouse cursor to hand when over clickable things
        is_clickable = hovered_action is not None
        # Palette area
        if panel_x <= mx <= panel_x + 100 and 50 <= my <= 50 + 250:
            is_clickable = True
        # Edit fields
        if selected_idx is not None:
            p_y = 320
            if panel_x <= mx <= panel_x + 140 and (p_y + 65 <= my <= p_y + 89 or p_y + 125 <= my <= p_y + 149):
                is_clickable = True
        # Image area (for buttons / creating)
        ix, iy, iw, ih = IMG_AREA
        if ix <= mx <= ix + iw and iy <= my <= iy + ih:
            is_clickable = True
        # Till names bar at bottom
        if win_h - 30 <= my <= win_h:
            is_clickable = True

        if is_clickable:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND)
        else:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)

        pygame.display.flip()
        clock.tick(60)

    save_buttons(button_data)
    pygame.quit()

def get_display_image_for_editor(img, max_w, max_h):
    """Returns (scaled_surface, (offset_x, offset_y), scale)"""
    scale = min(max_w / img.get_width(), max_h / img.get_height())
    new_w = int(img.get_width() * scale)
    new_h = int(img.get_height() * scale)
    scaled = pygame.transform.smoothscale(img, (new_w, new_h))
    ox = (max_w - new_w) // 2
    oy = (max_h - new_h) // 2
    return scaled, (ox, oy), scale

if __name__ == "__main__":
    main()