"""
Basic Item-to-Icon Mapper Tool

Similar to the till button editor, but for assigning which icon PNG
to use for each "take:" item (e.g. madriGlass -> madri_glass.png). take: items now use naming take:wordNewThing&AnotherThing (enforced by editor).

Run with:
    python -m src.bar.item_icon_tool

Saves to NeuroMods/Bar/item_icon_map.json
The game will prefer this map (with fallback to old logic).

Controls:
- Click item in left list to select
- Click icon in middle list to select (with preview)
- Click "Assign" to map selected item -> selected icon
- Click "Remove" to clear mapping for selected item
- Mouse wheel over lists to scroll
- Ctrl+S or click "Save" to save JSON
- ESC to quit
"""

import pygame
import json
from pathlib import Path
import sys

def _get_project_root():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent.parent

PROJECT_ROOT = _get_project_root()
IMAGES_ROOT = PROJECT_ROOT / "NeuroMods" / "Bar"
ITEM_IMAGES_DIR = IMAGES_ROOT / "Item Images"
MAP_FILE = IMAGES_ROOT / "item_icon_map.json"
BUTTONS_FILE = IMAGES_ROOT / "till_buttons.json"

def load_items_from_buttons():
    items = set()
    if BUTTONS_FILE.exists():
        with open(BUTTONS_FILE, "r") as f:
            data = json.load(f)
        for view, buttons in data.items():
            for btn in buttons:
                action = btn.get("action", "")
                if action.startswith("take:"):
                    item = action[5:].strip()
                    if item:
                        items.add(item)
    # Add some common ones from bar.nm / recipes if not in buttons
    # Use new take: naming scheme (camel&); legacy _ kept for transition
    extras = [
        "lemonSlice", "limeSlice", "orangeSlice",
        "bostonShakerTin",
        "tallGlass", "shortGlass",
        "125mlThimble", "50mlThimble", "25mlThimble",
        "shotsGlass",
        # legacy for mapper users with old data
        "lemon_slice", "lime_slice", "orange_slice",
        "boston_shaker_tin",
        "tall_glass", "short_glass",
        "125ml_thimble", "50ml_thimble", "25ml_thimble",
        "shots_glass",
    ]
    for e in extras:
        items.add(e)
    return sorted(items)

def load_available_icons():
    icons = []
    if ITEM_IMAGES_DIR.exists():
        for p in sorted(ITEM_IMAGES_DIR.glob("*.png")):
            icons.append(p.name)
    return icons

def load_map():
    if MAP_FILE.exists():
        with open(MAP_FILE, "r") as f:
            return json.load(f)
    return {}

def save_map(mappings):
    MAP_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MAP_FILE, "w") as f:
        json.dump(mappings, f, indent=2)

def main():
    pygame.init()
    screen = pygame.display.set_mode((1100, 700), pygame.RESIZABLE)
    pygame.display.set_caption("Item Icon Mapper - Assign icons to take: items (Shift+Click or buttons)")
    clock = pygame.time.Clock()
    from .ui_fonts import ui_font

    font = ui_font(18)
    small_font = ui_font(14)
    title_font = ui_font(24)

    items = load_items_from_buttons()
    available_icons = load_available_icons()
    mappings = load_map()

    # load previews (small)
    icon_previews = {}
    for name in available_icons:
        p = ITEM_IMAGES_DIR / name
        try:
            img = pygame.image.load(str(p)).convert_alpha()
            icon_previews[name] = img
        except Exception:
            pass

    selected_item = None
    selected_icon = None
    scroll_items = 0
    scroll_icons = 0
    scroll_mappings = 0
    editing_new_item = False
    new_item_text = ""

    running = True
    while running:
        win_w, win_h = screen.get_size()
        mx, my = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_s and (event.mod & pygame.KMOD_CTRL):
                    save_map(mappings)
                    print("Saved item_icon_map.json")
                elif editing_new_item:
                    if event.key == pygame.K_RETURN:
                        if new_item_text.strip():
                            items.append(new_item_text.strip())
                            items = sorted(set(items))
                            selected_item = new_item_text.strip()
                        editing_new_item = False
                        new_item_text = ""
                    elif event.key == pygame.K_BACKSPACE:
                        new_item_text = new_item_text[:-1]
                    elif event.unicode and event.unicode.isprintable():
                        new_item_text += event.unicode

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    # Items list (left)
                    if 10 < mx < 280 and 60 < my < win_h - 60:
                        idx = scroll_items + (my - 60) // 20
                        if 0 <= idx < len(items):
                            selected_item = items[idx]

                    # Icons list (middle)
                    if 300 < mx < 620 and 60 < my < win_h - 60:
                        idx = scroll_icons + (my - 60) // 20
                        if 0 <= idx < len(available_icons):
                            selected_icon = available_icons[idx]

                    # Buttons area (right)
                    btn_x = 640
                    if btn_x < mx < btn_x + 120:
                        if 80 < my < 105:  # Assign
                            if selected_item and selected_icon:
                                mappings[selected_item] = selected_icon
                                save_map(mappings)  # auto-save on assign for convenience
                        elif 115 < my < 140:  # Remove
                            if selected_item and selected_item in mappings:
                                del mappings[selected_item]
                                save_map(mappings)
                        elif 150 < my < 175:  # Save
                            save_map(mappings)
                            print("Saved item_icon_map.json")
                        elif 185 < my < 210:  # Add custom item
                            editing_new_item = True
                            new_item_text = ""

                elif event.button == 4:  # wheel up
                    if 10 < mx < 280:
                        scroll_items = max(0, scroll_items - 3)
                    elif 300 < mx < 620:
                        scroll_icons = max(0, scroll_icons - 3)
                    elif 640 < mx < win_w - 10:
                        scroll_mappings = max(0, scroll_mappings - 3)
                elif event.button == 5:  # wheel down
                    if 10 < mx < 280:
                        scroll_items = min(max(0, len(items) - 25), scroll_items + 3)
                    elif 300 < mx < 620:
                        scroll_icons = min(max(0, len(available_icons) - 25), scroll_icons + 3)
                    elif 640 < mx < win_w - 10:
                        scroll_mappings = min(max(0, len(mappings) - 20), scroll_mappings + 3)

            elif event.type == pygame.MOUSEWHEEL:
                if 10 < mx < 280:
                    scroll_items = max(0, scroll_items - event.y * 3)
                elif 300 < mx < 620:
                    scroll_icons = max(0, scroll_icons - event.y * 3)
                elif 640 < mx < win_w:
                    scroll_mappings = max(0, scroll_mappings - event.y * 3)

        screen.fill((35, 35, 40))

        # Title
        title = title_font.render("Item → Icon Mapper (for hand display)", True, (220, 220, 180))
        screen.blit(title, (20, 10))

        # Instructions
        instr = small_font.render("Click item | Click icon | Assign | Scroll lists with wheel | Ctrl+S to save | Shift+I in game to toggle icons on/off", True, (160, 160, 160))
        screen.blit(instr, (20, 35))

        # === Items list (left) ===
        pygame.draw.rect(screen, (25, 25, 28), (10, 55, 270, win_h - 110))
        y = 60
        visible_items = items[scroll_items:scroll_items + 28]
        for i, item in enumerate(visible_items):
            col = (200, 200, 200)
            bg = None
            if item == selected_item:
                bg = (60, 80, 100)
                col = (255, 255, 150)
            if bg:
                pygame.draw.rect(screen, bg, (12, y - 2, 266, 18))
            txt = font.render(item, True, col)
            screen.blit(txt, (15, y))
            y += 20

        # === Icons list (middle) ===
        pygame.draw.rect(screen, (25, 25, 28), (295, 55, 320, win_h - 110))
        y = 60
        visible_icons = available_icons[scroll_icons:scroll_icons + 28]
        for i, name in enumerate(visible_icons):
            col = (200, 200, 200)
            bg = None
            if name == selected_icon:
                bg = (60, 80, 100)
                col = (255, 255, 150)
            if bg:
                pygame.draw.rect(screen, bg, (297, y - 2, 316, 18))
            # small preview
            if name in icon_previews:
                prev = pygame.transform.smoothscale(icon_previews[name], (16, 16))
                screen.blit(prev, (300, y))
            txt = font.render(name, True, col)
            screen.blit(txt, (320, y))
            y += 20

        # === Preview + actions (right) ===
        pygame.draw.rect(screen, (25, 25, 28), (630, 55, win_w - 645, 200))
        if selected_icon and selected_icon in icon_previews:
            prev = pygame.transform.smoothscale(icon_previews[selected_icon], (80, 80))
            screen.blit(prev, (650, 70))
            txt = font.render(selected_icon, True, (220, 220, 180))
            screen.blit(txt, (740, 80))
        else:
            txt = font.render("(select an icon for preview)", True, (150, 150, 150))
            screen.blit(txt, (650, 100))

        if selected_item:
            txt = font.render(f"Selected item: {selected_item}", True, (255, 255, 200))
            screen.blit(txt, (650, 160))
            assigned = mappings.get(selected_item, "(none)")
            txt = font.render(f"Currently maps to: {assigned}", True, (180, 180, 180))
            screen.blit(txt, (650, 180))

        # Action buttons
        btn_x = 650
        btns = [
            (80, "Assign", (70, 120, 70)),
            (115, "Remove", (120, 70, 70)),
            (150, "Save JSON", (70, 70, 120)),
            (185, "Add custom item", (90, 90, 90)),
        ]
        for by, label, col in btns:
            pygame.draw.rect(screen, col, (btn_x, by, 140, 22))
            txt = small_font.render(label, True, (255, 255, 255))
            screen.blit(txt, (btn_x + 8, by + 4))

        # New item input
        if editing_new_item:
            pygame.draw.rect(screen, (50, 50, 60), (btn_x, 210, 140, 20))
            txt = small_font.render(new_item_text or "type name...", True, (255, 255, 200))
            screen.blit(txt, (btn_x + 4, 212))

        # === Current mappings (far right) ===
        pygame.draw.rect(screen, (20, 20, 23), (800, 55, win_w - 810, win_h - 110))
        txt = font.render("Current Mappings (item → icon)", True, (200, 200, 180))
        screen.blit(txt, (810, 60))
        y = 85
        for i, (item, icon) in enumerate(sorted(mappings.items())[scroll_mappings:]):
            if y > win_h - 70:
                break
            txt = small_font.render(f"{item} → {icon}", True, (180, 180, 180))
            screen.blit(txt, (810, y))
            y += 16

        pygame.display.flip()
        clock.tick(60)

    save_map(mappings)
    pygame.quit()
    print("Mapper closed. Mappings saved to", MAP_FILE)

if __name__ == "__main__":
    main()
