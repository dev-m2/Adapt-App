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
- The tool saves to NeuroMods/Bar/till_buttons.json
- Game automatically loads it

Images loaded from:
- Till screens: NeuroMods/Bar/Till Images/
- Position/spot views (new naming 1N1.jpg etc.): NeuroMods/Bar/Bar Images/
  New images added to Bar Images/ are automatically discovered.

Actions supported in game:
- "add_order:Item Name"   -> adds to orders, prints
- "send_order"            -> prints full order and clears
- "switch:till_food_burgers" or "switch:till_lager" -> changes to that till screen
- New send grades etc. also supported if defined in json

Colors: cyan, blue, yellow, white, red, purple, grey, orange, light orange, green, etc.
Add more in the COLORS dict below if needed.
"""

import pygame
import json
from pathlib import Path
import sys

# --- Path setup ---
def _get_project_root():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent.parent

PROJECT_ROOT = _get_project_root()
IMAGES_ROOT = PROJECT_ROOT / "NeuroMods" / "Bar"
BUTTONS_FILE = PROJECT_ROOT / "NeuroMods" / "Bar" / "till_buttons.json"

# --- Available views ---
# Till views use Till Images/ (keys must match those in game.py VIEWS and till_buttons.json)
TILL_VIEW_MAP = {
    "till_food_promo": "Till Images/bar till food - food promo.jpg",
    "till_food_meal_deal": "Till Images/bar till menu - meal deal.jpg",
    "till_food_kids_food": "Till Images/bar till food - kids.jpg",
    "till_food_desserts": "Till Images/bar till food - desserts.jpg",
    "till_food_meat_free": "Till Images/bar till food - meat free.jpg",
    "till_food_sides": "Till Images/bar till food - sides.jpg",
    "till_food_carvery": "Till Images/bar till food - carvery.jpg",
    "till_food_burgers": "Till Images/bar till food - burgers.jpg",
    "till_food": "Till Images/bar till - food screen.jpg",
    "till_promo": "Till Images/bar till drinks - drink promo.jpg",
    "till_kids": "Till Images/bar till drinks - kids.jpg",
    "till_crisps": "Till Images/bar till drinks - crisps.jpg",
    "till_bottles": "Till Images/bar till drinks - bottles.jpg",
    "till_wine": "Till Images/bar till drinks - wine.jpg",
    "till_spirits": "Till Images/bar till drinks - spirits.jpg",
    "till_soft": "Till Images/bar till drinks - soft.jpg",
    "till_bitter": "Till Images/bar till drinks - bitter and ale.jpg",
    "till_lager": "Till Images/bar till drinks - lager and cider.jpg",
    "till_n": "Till Images/bar till - bar screen.jpg",
}

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
    "till_food_promo",
    "till_food_meal_deal",
    "till_food_kids_food",
    "till_food_desserts",
    "till_food_meat_free",
    "till_food_sides",
    "till_food_carvery",
    "till_food_burgers",
    "till_food",
    "till_promo",
    "till_kids",
    "till_crisps",
    "till_bottles",
    "till_wine",
    "till_spirits",
    "till_soft",
    "till_bitter",
    "till_lager",
]
HOME_TILL = "till_n"

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
    print(f"Saved to {BUTTONS_FILE}")

def load_image(view):
    path = IMAGES_ROOT / VIEW_MAP[view]
    if not path.exists():
        print(f"Warning: Image not found {path}")
        return None
    return pygame.image.load(str(path)).convert()

def main():
    pygame.init()
    screen = pygame.display.set_mode((1280, 800))
    pygame.display.set_caption("Till Button Editor - Drag to draw, click to edit")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 24)
    small_font = pygame.font.SysFont(None, 20)

    button_data = load_buttons()  # { "till_n": [ {"rect": [...], "label":.., "color":.., "action":..}, ... ], ... }

    view_keys = VIEWS_ORDER  # ordered for arrow navigation
    current_view = "till_n"
    current_img = load_image(current_view)

    # Display area for the image
    IMG_AREA = (200, 30, 900, 650)  # x,y,w,h on screen

    selected_idx = None
    drawing = False
    drag_start = None

    # Simple text editing
    editing_label = False
    editing_action = False
    label_text = ""
    action_text = ""
    sugg_selected = 0

    running = True
    while running:
        screen.fill((40, 40, 45))

        # Compute action autocomplete suggestions based on previous actions in button_data
        current_suggestions = []
        if editing_action and selected_idx is not None and current_view in button_data:
            all_actions = set()
            for vbtns in button_data.values():
                for b in vbtns:
                    a = str(b.get("action", "")).strip()
                    if a:
                        all_actions.add(a)
            curr = action_text.lower().strip()
            if curr:
                current_suggestions = sorted(a for a in all_actions if curr in a.lower())[:8]
            else:
                current_suggestions = sorted(all_actions)[:8]

            # Clamp selection when suggestions change
            if current_suggestions:
                sugg_selected = min(sugg_selected, len(current_suggestions) - 1)
            else:
                sugg_selected = 0

        # Instructions (no sidebar list)
        inst = [
            "Left/Right arrows: switch view",
            "Drag on image: create new button",
            "Click existing box: select",
            "DEL: delete selected",
            "Click color swatches to change color",
            "Click Label/Action boxes to type (Enter to finish)",
            "Editing Action: Up/Down = navigate suggestions, Tab/Enter = accept",
            "S: Save   ESC: Quit"
        ]
        y = 550
        for line in inst:
            txt = small_font.render(line, True, (180, 180, 180))
            screen.blit(txt, (10, y))
            y += 18

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

                color_name = btn.get("color", "transparent black")
                color = COLORS.get(color_name, (30, 144, 255))

                if color_name == "transparent black":
                    s = pygame.Surface((sw, sh), pygame.SRCALPHA)
                    s.fill((0, 0, 0, 128))
                    screen.blit(s, (sx, sy))
                    text_col = (255, 255, 255)
                else:
                    pygame.draw.rect(screen, color, (sx, sy, sw, sh))  # fill with button color
                    text_col = (0, 0, 0) if color_name != "black" else (255, 255, 255)

                if i == selected_idx:
                    pygame.draw.rect(screen, (255, 255, 0), (sx-2, sy-2, sw+4, sh+4), 2)

                # Centered text
                lbl = small_font.render(btn.get("label", "?")[:20], True, text_col)
                text_x = sx + (sw - lbl.get_width()) // 2
                text_y = sy + (sh - lbl.get_height()) // 2
                screen.blit(lbl, (text_x, text_y))

        # --- Draw color palette (right side) ---
        palette_x = 1120
        palette_y = 50
        swatch_size = 28
        col = 0
        row = 0
        for name, rgb in COLORS.items():
            x = palette_x + (col * (swatch_size + 4))
            y = palette_y + (row * (swatch_size + 4))
            pygame.draw.rect(screen, rgb, (x, y, swatch_size, swatch_size))
            pygame.draw.rect(screen, (200,200,200), (x, y, swatch_size, swatch_size), 1)

            # label
            nm = small_font.render(name, True, (220,220,220))
            screen.blit(nm, (x, y + swatch_size + 1))

            col += 1
            if col > 2:
                col = 0
                row += 1

        # --- Editing panel (when something selected) ---
        if selected_idx is not None and selected_idx < len(view_btns):
            btn = view_btns[selected_idx]
            panel_x = 1120
            panel_y = 320

            # Color label
            screen.blit(font.render("Color:", True, (255,255,255)), (panel_x, panel_y))

            # Current color swatch
            cur_color = COLORS.get(btn.get("color", "transparent black"), (100,100,100))
            pygame.draw.rect(screen, cur_color, (panel_x + 70, panel_y, 40, 25))
            screen.blit(small_font.render(btn.get("color", "transparent black"), True, (200,200,200)), (panel_x + 115, panel_y + 3))

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
                "add_order:Madri",
                "switch:till_food_burgers",
                "send_order"
            ]
            hy = panel_y + 300
            for h in help_lines:
                screen.blit(small_font.render(h, True, (150,150,150)), (panel_x, hy))
                hy += 16

        # --- Current view label ---
        screen.blit(font.render(f"Current: {current_view}", True, (255,255,100)), (IMG_AREA[0], 5))

        # --- Event handling ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
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
                                btn["action"] = action_text
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

            if event.type == pygame.MOUSEBUTTONDOWN and current_img:
                mx, my = event.pos

                # Autocomplete: click a suggestion to accept it (check BEFORE auto-save)
                if editing_action and current_suggestions and selected_idx is not None and current_view in button_data:
                    panel_y = 320
                    sug_y = panel_y + 150
                    for ii, sug in enumerate(current_suggestions):
                        if 1120 <= mx <= 1120 + 220 and sug_y + ii * 16 <= my <= sug_y + (ii + 1) * 16:
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
                            btn["action"] = action_text
                    editing_label = editing_action = False
                    sugg_selected = 0

                # Check click on color swatches
                if selected_idx is not None and current_view in button_data:
                    palette_x = 1120
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
                    if  panel_y + 65 <= my <= panel_y + 89 and 1120 <= mx <= 1260:
                        editing_label = True
                        editing_action = False
                        label_text = button_data[current_view][selected_idx].get("label", "")
                    elif panel_y + 125 <= my <= panel_y + 149 and 1120 <= mx <= 1260:
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
                            "label": "Take",
                            "color": "transparent black",
                            "action": "take:"
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
            pygame.draw.rect(screen, (255, 255, 0), (sx, sy, sw, sh), 2)

        # --- Draw current selected info ---
        if selected_idx is not None and current_view in button_data and selected_idx < len(button_data[current_view]):
            btn = button_data[current_view][selected_idx]
            info_y = 700
            screen.blit(font.render(f"Selected: {btn['label']}", True, (255,255,0)), (200, info_y))
            screen.blit(small_font.render(f"Action: {btn['action']}", True, (200,200,200)), (200, info_y + 22))
            screen.blit(small_font.render(f"Color: {btn.get('color','transparent black')}", True, (200,200,200)), (200, info_y + 40))

        pygame.display.flip()
        clock.tick(60)

    save_buttons(button_data)
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