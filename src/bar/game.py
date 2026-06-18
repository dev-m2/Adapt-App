"""
Minimal Pygame demo for basic bar navigation.

Goal for this first iteration:
- Load real photos from NeuroMods/Bar/Bar Images/ (positions) and Till Images/ (tills)
- Simple left / right movement between discrete views
- Demonstrate the "View" concept the user described (image + neighbors)
- Some directions can be invalid (e.g. forward/back when facing a shelf)
- Click anywhere prints the click location in ORIGINAL image pixels
  (super useful for defining hotspots later)

Run:
    python -m src.bar.game
or (from project root):
    python src/bar/game.py

You will need:
    pip install pygame

Controls (in addition to the on-screen help):
- A/D: move relative to facing (reverses automatically when south-facing)
- Arrow keys: move absolute west/east
- Q/E: turn
- Ctrl (or C): toggle crouch/stand (single button toggle when relevant)
- All photo buttons (including any top BAR/FOOD switch buttons) now come from the editor tool (JSON); take: actions use scheme take:wordNewThing&AnotherThing (autocomplete cross with order: in tool); void: undoes the last added order item; opener: opens sealed bottles in-hand to *Opened; thimble:25/50/125 for measuring wines and spirits in-hand (not softs, cans, beer, crisps, etc.)
- Click: print original image coords for hotspots
- Shift+O: toggle console log (for seeing prints in fullscreen)
- Shift+I: toggle hand icons (text mode is default)
- Ctrl+Q: quit
- W (on any till screen): go to customer screen
- S (on any till screen): leave the till to the bar (re-opens at tillDrinks next time)
- S (on customer screen): return to the till screen you came from
- ESC: return from till sub-menus to tillDrinks (not used for quitting)

The view graph now models multiple positions + north/south facing + stand/crouch
(where photos exist). This will be revised with your next set of images.
"""

from __future__ import annotations

import csv
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional
import random
import json

from .customer_screen import (
    AIcomputeCustomerLayout,
    AIdrawCustomerBackground,
    AIdrawCustomerPortrait,
    AIloadCustomerRoster,
    AIpickRandomCustomer,
    CustomerEntry,
    load_customer_frame_surface,
    load_customer_headshot_surface,
    load_customer_viewport,
)
from .demand_display import format_counter_item, format_customer_demand
from .ui_fonts import font_status, ui_font
from . import ui_theme
from .till_frame import (
    blit_rounded_surface,
    layout_view_photo,
    load_till_frame_surface,
    load_till_viewport,
)
from .item_types import (
    BEER_GLASS_BASES,
    DEMAND_WEIGHT_MAP,
    can_open_with_opener,
    can_thimble,
    classify_item_type,
    combine_measured_pours,
    is_measured_pour,
    strip_thimble_suffix,
    try_open_bottle,
    try_spirit_shot_pour,
)

# Pygame is imported lazily inside run_demo() so that you can import this module
# for path testing / data inspection without needing pygame installed.
pygame = None  # will be set at runtime

# ---------------------------------------------------------------------------
# State for bar review sessions (driven from src/core/main.py when a "bar" type
# due card is reviewed). run_bar_review_session() populates these; run_demo()
# consults them for demand selection and for applying FSRS grades on finish.
# ---------------------------------------------------------------------------
_review_mode = False
_due_map: dict = {}          # demand_key (from response) -> adapt_id (str)
_practice_mode = False


def _session_mode_label() -> str:
    """Human-readable session mode for UI (window title, loading screen)."""
    if _review_mode and not _practice_mode:
        return "Review Mode"
    return "Practice Mode"


def _window_caption() -> str:
    return f"Adapt App - Bar Trainer ({_session_mode_label()})"


def _sample_next_demands():
    """Choose 3-6 demands. While there are still due bar cards in review mode,
    prefer sampling from the remaining due ones. Falls back to weighted sampling
    from the full potential orders list (derived from buttons that have both
    a take:/pour: and an order: button).

    Weights come from the 'type' of the order:
      food=1.0, side=0.25, extra=0.25, wine/spirit/beer/soft/can/bottleBeer/barFood/kids/other=1.0
    """
    global _review_mode, _due_map, _practice_mode
    if _review_mode and _due_map:
        keys = list(_due_map.keys())
        k = min(len(keys), random.randint(3, 6))
        if k > 0:
            return random.sample(keys, k=k)

    demands = load_potential_orders()
    if not demands:
        # minimal fallback (avoid empty-glass bases which are excluded from potential)
        return ["cokeCan", "chipsWalkersCheese&Onion", "foodBigstackBurger"]

    if isinstance(demands[0], dict):
        pop = [d["key"] for d in demands]
        weights = [d.get("weight", 1.0) for d in demands]
    else:
        # old format (list of str)
        pop = demands
        weights = [1.0] * len(pop)

    k = random.randint(3, 6)
    # Weighted sampling (with possible dups in theory, but k << N so rare)
    sampled = random.choices(pop, weights=weights, k=k)

    # Deduplicate while preserving order (prefer distinct demands)
    seen = set()
    result = []
    for s in sampled:
        if s not in seen:
            seen.add(s)
            result.append(s)
    return result


def load_potential_orders():
    """Load the list of valid potential customer orders.

    Returns list of dicts:
      {'key': 'foodBigstackBurger', 'Display': 'a Bigstack Burger', 'type': 'food', 'weight': 1.0}
      ...

    These are items for which the till_buttons.json defines BOTH:
      - A take: or pour: button (so you can acquire/place the item in a hand)
      - An order: button (so the item can be sent from the till)

    Item types (see src/bar/item_types.py): wine, spirit, beer, soft, can, bottleBeer,
    barFood (crisps), kids, food/side/extra, emptyGlass (excluded), other.
    Thimble works on wine and spirit only (not softs, cans, beer, crisps, kids drinks, etc.).

    The list is maintained by running src/bar/genOrders.py (python -m src.bar.genOrders)
    (which also writes NeuroMods/Bar/BarGame.nm as content,source CSV rows).

    Each BarGame.nm row stores {"type": "bar", "cue": customer line, "response": order key}.
    Item category and practice weights are derived from the response key at load time.

    Used for (weighted) practice-mode (non-review) customer demand generation.
    """
    try:
        bar_root = _get_bar_images_root()
        nm_path = bar_root / "BarGame.nm"
        if nm_path.exists():
            items = []
            with open(nm_path, "r", encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    raw = (row.get("content") or "").strip()
                    if not raw:
                        continue
                    try:
                        content = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if content.get("type") != "bar":
                        continue
                    key = content.get("response")
                    if not isinstance(key, str) or not key:
                        continue
                    display = content.get("cue") or format_customer_demand(key)
                    typ = classify_item_type(key)
                    w = DEMAND_WEIGHT_MAP.get(typ, 1.0)
                    items.append({
                        "key": key,
                        "Display": display,
                        "type": typ,
                        "weight": w,
                    })
            if items:
                return items
    except Exception as e:
        print("Warning: could not load BarGame.nm:", e)
    # Fallback: a few common ones (as structured) so the game is still playable
    # (avoid using beer glass bases, which have emptyGlass type and are excluded)
    fallback_keys = ["cokeCan", "chipsWalkersCheese&Onion", "foodBigstackBurger", "guinessCanZero"]
    return [{"key": k, "Display": format_customer_demand(k), "type": "other", "weight": 1.0} for k in fallback_keys]



# ---------------------------------------------------------------------------
# Path resolution (works when run as module, as script, or frozen later)
# ---------------------------------------------------------------------------

def _get_bar_images_root() -> Path:
    """
    Resolve the NeuroMods/Bar root containing Bar Images/ and Till Images/.
    We no longer use placeholder_images/.
    """
    # Best case: import from core (respects PyInstaller frozen layout)
    try:
        from ..core.utils import NEURO_MODS_DIR  # type: ignore
        candidate = NEURO_MODS_DIR / "Bar"
        if candidate.exists():
            return candidate
    except Exception:
        pass

    # Fallbacks for development (running this file directly)
    here = Path(__file__).resolve().parent

    # src/bar/game.py → project_root / NeuroMods / Bar
    for parent in (here.parent.parent, here.parent.parent.parent):
        cand = parent / "NeuroMods" / "Bar"
        if cand.exists():
            return cand

    # Last resort: relative to current working directory
    cand = Path("NeuroMods/Bar")
    if cand.exists():
        return cand

    raise FileNotFoundError(
        "Could not locate NeuroMods/Bar/ (with Bar Images/ and Till Images/ subfolders).\n"
        "Run this script from the project root or make sure the folder exists."
    )


# ---------------------------------------------------------------------------
# View model (directly inspired by your description)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class View:
    """A discrete view of the bar.

    This is pure data (easy to serialize to JSON later if we want).
    The .go() method lets a view answer "what is to my right/left/etc?"
    Some directions return None when they don't make sense
    (e.g. you turned to face a glass shelf — there is no 'forward' from there).
    """
    key: str
    image_path: str          # relative to the Bar root, e.g. "Bar Images/1N1.jpg" or "Till Images/tillDrinks.jpg"
    name: str
    # Directions that are meaningful from this exact view + orientation + height
    neighbors: Dict[str, Optional[str]]

    def go(self, direction: str) -> Optional[str]:
        """Return the key of the view in that direction, or None if impossible."""
        return self.neighbors.get(direction)


# ---------------------------------------------------------------------------
# New layout (Bar Images/ using SpotDirectionHeight naming, e.g. 1E1.jpg = spot 1 East standing)
# ---------------------------------------------------------------------------
# Bar runs west (spot 1) → east (spot 7).
# Directions N/S/E/W = facing. Height 1=stand 0=crouch.
# Till images kept in Till Images/. Old position images (a*/b*/c* etc.) are no longer used.
# left/right: move along bar (S facing reverses player left/right via is_south_facing).
# Q/E: turn (cycles N-E-S-W at same spot/height if photo exists).
# Ctrl: height toggle (crouch/stand) if pair exists.
# Spot 1 N/S/W specially wired to tillDrinks (and back). New views start clean (no buttons).

VIEWS: Dict[str, View] = {
    # === North facing (stand) - previous a-series + till ===
    "tillDrinks": View(
        key="tillDrinks",
        image_path="Till Images/tillDrinks.jpg",
        name="Till (west-most, north stand)",
        neighbors={
            "left": None,
            "right": "1N1",
            "forward": "customer",
            "back": "1W1",
            "turn_left": "1S0",
            "turn_right": "1S0",
            "crouch": None,
            "stand": None,
        },
    ),
    # === New bar positions (SpotDirHeight from Bar Images/) ===
    "1N0": View(
        key="1N0",
        image_path="Bar Images/1N0.jpg",
        name="Spot 1 facing N (height 0)",
        neighbors={'left': 'tillDrinks', 'right': '2N0', 'forward': None, 'back': None, 'turn_left': '1W0', 'turn_right': None, 'crouch': None, 'stand': '1N1'},
    ),
    "1N1": View(
        key="1N1",
        image_path="Bar Images/1N1.jpg",
        name="Spot 1 facing N (height 1)",
        neighbors={'left': 'tillDrinks', 'right': '2N1', 'forward': None, 'back': None, 'turn_left': None, 'turn_right': '1E1', 'crouch': '1N0', 'stand': None},
    ),
    "1S0": View(
        key="1S0",
        image_path="Bar Images/1S0.jpg",
        name="Spot 1 facing S (height 0)",
        neighbors={'left': '2S0', 'right': None, 'forward': None, 'back': None, 'turn_left': 'tillDrinks', 'turn_right': 'tillDrinks', 'crouch': None, 'stand': None},
    ),
    "1E1": View(
        key="1E1",
        image_path="Bar Images/1E1.jpg",
        name="Spot 1 facing E (height 1)",
        neighbors={'left': None, 'right': None, 'forward': '2E1', 'back': None, 'turn_left': '1N1', 'turn_right': None, 'crouch': None, 'stand': None},
    ),
    "1W0": View(
        key="1W0",
        image_path="Bar Images/1W0.jpg",
        name="Spot 1 facing W (height 0)",
        neighbors={'left': None, 'right': None, 'forward': 'tillDrinks', 'back': '2W0', 'turn_left': None, 'turn_right': '1N0', 'crouch': None, 'stand': '1W1'},
    ),
    "1W1": View(
        key="1W1",
        image_path="Bar Images/1W1.jpg",
        name="Spot 1 facing W (height 1)",
        neighbors={'left': None, 'right': None, 'forward': 'tillDrinks', 'back': '2W1', 'turn_left': None, 'turn_right': '1N1', 'crouch': '1W0', 'stand': None},
    ),
    "2N0": View(
        key="2N0",
        image_path="Bar Images/2N0.jpg",
        name="Spot 2 facing N (height 0)",
        neighbors={'left': '1N0', 'right': '3N0', 'forward': None, 'back': None, 'turn_left': '2W0', 'turn_right': None, 'crouch': None, 'stand': '2N1'},
    ),
    "2N1": View(
        key="2N1",
        image_path="Bar Images/2N1.jpg",
        name="Spot 2 facing N (height 1)",
        neighbors={'left': '1N1', 'right': '3N1', 'forward': None, 'back': None, 'turn_left': None, 'turn_right': '2E1', 'crouch': '2N0', 'stand': None},
    ),
    "2S0": View(
        key="2S0",
        image_path="Bar Images/2S0.jpg",
        name="Spot 2 facing S (height 0)",
        neighbors={'left': '3S0', 'right': '1S0', 'forward': None, 'back': None, 'turn_left': None, 'turn_right': '2W0', 'crouch': None, 'stand': '2S1'},
    ),
    "2S1": View(
        key="2S1",
        image_path="Bar Images/2S1.jpg",
        name="Spot 2 facing S (height 1)",
        neighbors={'left': '3S1', 'right': None, 'forward': None, 'back': None, 'turn_left': None, 'turn_right': '2W1', 'crouch': '2S0', 'stand': None},
    ),
    "2E1": View(
        key="2E1",
        image_path="Bar Images/2E1.jpg",
        name="Spot 2 facing E (height 1)",
        neighbors={'left': None, 'right': None, 'forward': '3E1', 'back': '1E1', 'turn_left': None, 'turn_right': '2S1', 'crouch': None, 'stand': None},
    ),
    "2W0": View(
        key="2W0",
        image_path="Bar Images/2W0.jpg",
        name="Spot 2 facing W (height 0)",
        neighbors={'left': None, 'right': None, 'forward': '1W0', 'back': '3W0', 'turn_left': None, 'turn_right': '2N0', 'crouch': None, 'stand': '2W1'},
    ),
    "2W1": View(
        key="2W1",
        image_path="Bar Images/2W1.jpg",
        name="Spot 2 facing W (height 1)",
        neighbors={'left': None, 'right': None, 'forward': '1W1', 'back': '3W1', 'turn_left': None, 'turn_right': '2N1', 'crouch': '2W0', 'stand': None},
    ),
    "3N0": View(
        key="3N0",
        image_path="Bar Images/3N0.jpg",
        name="Spot 3 facing N (height 0)",
        neighbors={'left': '2N0', 'right': '4N0', 'forward': None, 'back': None, 'turn_left': None, 'turn_right': '3E0', 'crouch': None, 'stand': '3N1'},
    ),
    "3N1": View(
        key="3N1",
        image_path="Bar Images/3N1.jpg",
        name="Spot 3 facing N (height 1)",
        neighbors={'left': '2N1', 'right': '4N1', 'forward': None, 'back': None, 'turn_left': None, 'turn_right': '3E1', 'crouch': '3N0', 'stand': None},
    ),
    "3S0": View(
        key="3S0",
        image_path="Bar Images/3S0.jpg",
        name="Spot 3 facing S (height 0)",
        neighbors={'left': '4S0', 'right': '2S0', 'forward': None, 'back': None, 'turn_left': None, 'turn_right': '3W0', 'crouch': None, 'stand': '3S1'},
    ),
    "3S1": View(
        key="3S1",
        image_path="Bar Images/3S1.jpg",
        name="Spot 3 facing S (height 1)",
        neighbors={'left': '4S1', 'right': '2S1', 'forward': None, 'back': None, 'turn_left': None, 'turn_right': '3W1', 'crouch': '3S0', 'stand': None},
    ),
    "3E0": View(
        key="3E0",
        image_path="Bar Images/3E0.jpg",
        name="Spot 3 facing E (height 0)",
        neighbors={'left': None, 'right': None, 'forward': '4E0', 'back': '2E0', 'turn_left': None, 'turn_right': '3S0', 'crouch': None, 'stand': '3E1'},
    ),
    "3E1": View(
        key="3E1",
        image_path="Bar Images/3E1.jpg",
        name="Spot 3 facing E (height 1)",
        neighbors={'left': None, 'right': None, 'forward': '4E1', 'back': '2E1', 'turn_left': None, 'turn_right': '3S1', 'crouch': '3E0', 'stand': None},
    ),
    "3W0": View(
        key="3W0",
        image_path="Bar Images/3W0.jpg",
        name="Spot 3 facing W (height 0)",
        neighbors={'left': None, 'right': None, 'forward': '2W0', 'back': '4W0', 'turn_left': None, 'turn_right': '3N0', 'crouch': None, 'stand': '3W1'},
    ),
    "3W1": View(
        key="3W1",
        image_path="Bar Images/3W1.jpg",
        name="Spot 3 facing W (height 1)",
        neighbors={'left': None, 'right': None, 'forward': '2W1', 'back': '4W1', 'turn_left': None, 'turn_right': '3N1', 'crouch': '3W0', 'stand': None},
    ),
    "4N0": View(
        key="4N0",
        image_path="Bar Images/4N0.jpg",
        name="Spot 4 facing N (height 0)",
        neighbors={'left': '3N0', 'right': '5N0', 'forward': None, 'back': None, 'turn_left': None, 'turn_right': '4E0', 'crouch': None, 'stand': '4N1'},
    ),
    "4N1": View(
        key="4N1",
        image_path="Bar Images/4N1.jpg",
        name="Spot 4 facing N (height 1)",
        neighbors={'left': '3N1', 'right': '5N1', 'forward': None, 'back': None, 'turn_left': None, 'turn_right': '4E1', 'crouch': '4N0', 'stand': None},
    ),
    "4S0": View(
        key="4S0",
        image_path="Bar Images/4S0.jpg",
        name="Spot 4 facing S (height 0)",
        neighbors={'left': '5S0', 'right': '3S0', 'forward': None, 'back': None, 'turn_left': None, 'turn_right': '4W0', 'crouch': None, 'stand': '4S1'},
    ),
    "4S1": View(
        key="4S1",
        image_path="Bar Images/4S1.jpg",
        name="Spot 4 facing S (height 1)",
        neighbors={'left': '5S1', 'right': '3S1', 'forward': None, 'back': None, 'turn_left': None, 'turn_right': '4W1', 'crouch': '4S0', 'stand': None},
    ),
    "4E0": View(
        key="4E0",
        image_path="Bar Images/4E0.jpg",
        name="Spot 4 facing E (height 0)",
        neighbors={'left': None, 'right': None, 'forward': '5E0', 'back': '3E0', 'turn_left': None, 'turn_right': '4S0', 'crouch': None, 'stand': '4E1'},
    ),
    "4E1": View(
        key="4E1",
        image_path="Bar Images/4E1.jpg",
        name="Spot 4 facing E (height 1)",
        neighbors={'left': None, 'right': None, 'forward': '5E1', 'back': '3E1', 'turn_left': None, 'turn_right': '4S1', 'crouch': '4E0', 'stand': None},
    ),
    "4W0": View(
        key="4W0",
        image_path="Bar Images/4W0.jpg",
        name="Spot 4 facing W (height 0)",
        neighbors={'left': None, 'right': None, 'forward': '3W0', 'back': '5W0', 'turn_left': None, 'turn_right': '4N0', 'crouch': None, 'stand': '4W1'},
    ),
    "4W1": View(
        key="4W1",
        image_path="Bar Images/4W1.jpg",
        name="Spot 4 facing W (height 1)",
        neighbors={'left': None, 'right': None, 'forward': '3W1', 'back': '5W1', 'turn_left': None, 'turn_right': '4N1', 'crouch': '4W0', 'stand': None},
    ),
    "5N0": View(
        key="5N0",
        image_path="Bar Images/5N0.jpg",
        name="Spot 5 facing N (height 0)",
        neighbors={'left': '4N0', 'right': '6N0', 'forward': None, 'back': None, 'turn_left': None, 'turn_right': '5E0', 'crouch': None, 'stand': '5N1'},
    ),
    "5N1": View(
        key="5N1",
        image_path="Bar Images/5N1.jpg",
        name="Spot 5 facing N (height 1)",
        neighbors={'left': '4N1', 'right': '6N1', 'forward': None, 'back': None, 'turn_left': None, 'turn_right': '5E1', 'crouch': '5N0', 'stand': None},
    ),
    "5S0": View(
        key="5S0",
        image_path="Bar Images/5S0.jpg",
        name="Spot 5 facing S (height 0)",
        neighbors={'left': '6S0', 'right': '4S0', 'forward': None, 'back': None, 'turn_left': None, 'turn_right': '5W0', 'crouch': None, 'stand': '5S1'},
    ),
    "5S1": View(
        key="5S1",
        image_path="Bar Images/5S1.jpg",
        name="Spot 5 facing S (height 1)",
        neighbors={'left': '6S1', 'right': '4S1', 'forward': None, 'back': None, 'turn_left': None, 'turn_right': '5W1', 'crouch': '5S0', 'stand': None},
    ),
    "5E0": View(
        key="5E0",
        image_path="Bar Images/5E0.jpg",
        name="Spot 5 facing E (height 0)",
        neighbors={'left': None, 'right': None, 'forward': '6E0', 'back': '4E0', 'turn_left': None, 'turn_right': '5S0', 'crouch': None, 'stand': '5E1'},
    ),
    "5E1": View(
        key="5E1",
        image_path="Bar Images/5E1.jpg",
        name="Spot 5 facing E (height 1)",
        neighbors={'left': None, 'right': None, 'forward': '6E1', 'back': '4E1', 'turn_left': None, 'turn_right': '5S1', 'crouch': '5E0', 'stand': None},
    ),
    "5W0": View(
        key="5W0",
        image_path="Bar Images/5W0.jpg",
        name="Spot 5 facing W (height 0)",
        neighbors={'left': None, 'right': None, 'forward': '4W0', 'back': '6W0', 'turn_left': None, 'turn_right': '5N0', 'crouch': None, 'stand': '5W1'},
    ),
    "5W1": View(
        key="5W1",
        image_path="Bar Images/5W1.jpg",
        name="Spot 5 facing W (height 1)",
        neighbors={'left': None, 'right': None, 'forward': '4W1', 'back': '6W1', 'turn_left': None, 'turn_right': '5N1', 'crouch': '5W0', 'stand': None},
    ),
    "6N0": View(
        key="6N0",
        image_path="Bar Images/6N0.jpg",
        name="Spot 6 facing N (height 0)",
        neighbors={'left': '5N0', 'right': None, 'forward': None, 'back': None, 'turn_left': None, 'turn_right': '6E0', 'crouch': None, 'stand': '6N1'},
    ),
    "6N1": View(
        key="6N1",
        image_path="Bar Images/6N1.jpg",
        name="Spot 6 facing N (height 1)",
        neighbors={'left': '5N1', 'right': None, 'forward': None, 'back': None, 'turn_left': None, 'turn_right': '6E1', 'crouch': '6N0', 'stand': None},
    ),
    "6S0": View(
        key="6S0",
        image_path="Bar Images/6S0.jpg",
        name="Spot 6 facing S (height 0)",
        neighbors={'left': '7S0', 'right': '5S0', 'forward': None, 'back': None, 'turn_left': None, 'turn_right': '6W0', 'crouch': None, 'stand': '6S1'},
    ),
    "6S1": View(
        key="6S1",
        image_path="Bar Images/6S1.jpg",
        name="Spot 6 facing S (height 1)",
        neighbors={'left': '7S1', 'right': '5S1', 'forward': None, 'back': None, 'turn_left': None, 'turn_right': '6W1', 'crouch': '6S0', 'stand': None},
    ),
    "6E0": View(
        key="6E0",
        image_path="Bar Images/6E0.jpg",
        name="Spot 6 facing E (height 0)",
        neighbors={'left': None, 'right': None, 'forward': '7E0', 'back': '5E0', 'turn_left': None, 'turn_right': '6S0', 'crouch': None, 'stand': '6E1'},
    ),
    "6E1": View(
        key="6E1",
        image_path="Bar Images/6E1.jpg",
        name="Spot 6 facing E (height 1)",
        neighbors={'left': None, 'right': None, 'forward': '7E1', 'back': '5E1', 'turn_left': None, 'turn_right': '6S1', 'crouch': '6E0', 'stand': None},
    ),
    "6W0": View(
        key="6W0",
        image_path="Bar Images/6W0.jpg",
        name="Spot 6 facing W (height 0)",
        neighbors={'left': None, 'right': None, 'forward': '5W0', 'back': '7W0', 'turn_left': None, 'turn_right': '6N0', 'crouch': None, 'stand': '6W1'},
    ),
    "6W1": View(
        key="6W1",
        image_path="Bar Images/6W1.jpg",
        name="Spot 6 facing W (height 1)",
        neighbors={'left': None, 'right': None, 'forward': '5W1', 'back': '7W1', 'turn_left': None, 'turn_right': '6N1', 'crouch': '6W0', 'stand': None},
    ),
    "7S0": View(
        key="7S0",
        image_path="Bar Images/7S0.jpg",
        name="Spot 7 facing S (height 0)",
        neighbors={'left': None, 'right': '6S0', 'forward': None, 'back': None, 'turn_left': None, 'turn_right': '7W0', 'crouch': None, 'stand': '7S1'},
    ),
    "7S1": View(
        key="7S1",
        image_path="Bar Images/7S1.jpg",
        name="Spot 7 facing S (height 1)",
        neighbors={'left': None, 'right': '6S1', 'forward': None, 'back': None, 'turn_left': None, 'turn_right': '7W1', 'crouch': '7S0', 'stand': None},
    ),
    "7E0": View(
        key="7E0",
        image_path="Bar Images/7E0.jpg",
        name="Spot 7 facing E (height 0)",
        neighbors={'left': None, 'right': None, 'forward': None, 'back': '6E0', 'turn_left': None, 'turn_right': '7S0', 'crouch': None, 'stand': '7E1'},
    ),
    "7E1": View(
        key="7E1",
        image_path="Bar Images/7E1.jpg",
        name="Spot 7 facing E (height 1)",
        neighbors={'left': None, 'right': None, 'forward': None, 'back': '6E1', 'turn_left': None, 'turn_right': '7S1', 'crouch': '7E0', 'stand': None},
    ),
    "7W0": View(
        key="7W0",
        image_path="Bar Images/7W0.jpg",
        name="Spot 7 facing W (height 0)",
        neighbors={'left': None, 'right': None, 'forward': '6W0', 'back': None, 'turn_left': '7S0', 'turn_right': None, 'crouch': None, 'stand': '7W1'},
    ),
    "7W1": View(
        key="7W1",
        image_path="Bar Images/7W1.jpg",
        name="Spot 7 facing W (height 1)",
        neighbors={'left': None, 'right': None, 'forward': '6W1', 'back': None, 'turn_left': '7S1', 'turn_right': None, 'crouch': '7W0', 'stand': None},
    ),

    # === Till bar menu sub-screens ===
    # These are special interactive views for the till station (not part of bar line movement).
    # Clicking tabs on the main tillDrinks screen switches to these.
    # Clicking in a sub-menu returns to tillDrinks (see click handling).
    # Till names use camelCase matching the new image filenames (e.g. tillDrinksLager, tillFoodCarvery).
    "tillDrinksLager": View(
        key="tillDrinksLager",
        image_path="Till Images/tillDrinksLager.jpg",
        name="Till Submenu: Lager + Cider",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "tillDrinksBitter": View(
        key="tillDrinksBitter",
        image_path="Till Images/tillDrinksBitter.jpg",
        name="Till Submenu: Bitter + Ale",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "tillDrinksSofts": View(
        key="tillDrinksSofts",
        image_path="Till Images/tillDrinksSofts.jpg",
        name="Till Submenu: Softs",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "tillDrinksSpirits": View(
        key="tillDrinksSpirits",
        image_path="Till Images/tillDrinksSpirits.jpg",
        name="Till Submenu: Spirits",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "tillDrinksWineRed125": View(
        key="tillDrinksWineRed125",
        image_path="Till Images/tillDrinksWineRed125.jpg",
        name="Till Submenu: Wine (Red 125ml)",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "tillDrinksBottlesLager": View(
        key="tillDrinksBottlesLager",
        image_path="Till Images/tillDrinksBottlesLager.jpg",
        name="Till Submenu: Bottles (Lager)",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "tillDrinksCrisps": View(
        key="tillDrinksCrisps",
        image_path="Till Images/tillDrinksCrisps.jpg",
        name="Till Submenu: Crisps",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "tillDrinksKids": View(
        key="tillDrinksKids",
        image_path="Till Images/tillDrinksKids.jpg",
        name="Till Submenu: Kids Drinks",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),

    # === Till food menu views (home + subs) ===
    "tillFood": View(
        key="tillFood",
        image_path="Till Images/tillFood.jpg",
        name="Till Food Screen (home)",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "tillFoodBurgers": View(
        key="tillFoodBurgers",
        image_path="Till Images/tillFoodBurgers.jpg",
        name="Till Food: Burgers",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "tillFoodCarvery": View(
        key="tillFoodCarvery",
        image_path="Till Images/tillFoodCarvery.jpg",
        name="Till Food: Carvery",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "tillFoodSides": View(
        key="tillFoodSides",
        image_path="Till Images/tillFoodSides.jpg",
        name="Till Food: Sides",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "tillFoodMeatFree": View(
        key="tillFoodMeatFree",
        image_path="Till Images/tillFoodSides.jpg",  # approx, adjust if exact file differs
        name="Till Food: Meat Free",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "tillFoodDesserts": View(
        key="tillFoodDesserts",
        image_path="Till Images/tillFoodDesserts.jpg",
        name="Till Food: Desserts",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "tillFoodKids": View(
        key="tillFoodKids",
        image_path="Till Images/tillFoodKids.jpg",
        name="Till Food: Kids",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "tillFoodMealdeal": View(
        key="tillFoodMealdeal",
        image_path="Till Images/tillFoodMealdeal.jpg",
        name="Till Food: Meal Deal",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "tillFoodPromo": View(
        key="tillFoodPromo",
        image_path="Till Images/tillFood.jpg",  # or specific if added
        name="Till Food: Food Promo",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    # Additional new camelCase till sub-views from updated Till Images (for switch: support)
    "tillDrinksSoftsDashes": View(key="tillDrinksSoftsDashes", image_path="Till Images/tillDrinksSoftsDashes.jpg", name="Till Submenu: Softs Dashes", neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None}),
    "tillDrinksSoftsDraught": View(key="tillDrinksSoftsDraught", image_path="Till Images/tillDrinksSoftsDraught.jpg", name="Till Submenu: Softs Draught", neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None}),
    "tillDrinksSoftsMixers": View(key="tillDrinksSoftsMixers", image_path="Till Images/tillDrinksSoftsMixers.jpg", name="Till Submenu: Softs Mixers", neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None}),
    "tillDrinksSoftsMocktail": View(key="tillDrinksSoftsMocktail", image_path="Till Images/tillDrinksSoftsMocktail.jpg", name="Till Submenu: Softs Mocktail", neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None}),
    "tillDrinksSoftsWater": View(key="tillDrinksSoftsWater", image_path="Till Images/tillDrinksSoftsWater.jpg", name="Till Submenu: Softs Water", neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None}),
    "tillDrinksSpiritsCocktails": View(key="tillDrinksSpiritsCocktails", image_path="Till Images/tillDrinksSpiritsCocktails.jpg", name="Till Submenu: Spirits Cocktails", neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None}),
    "tillDrinksSpiritsGin": View(key="tillDrinksSpiritsGin", image_path="Till Images/tillDrinksSpiritsGin.jpg", name="Till Submenu: Spirits Gin", neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None}),
    "tillDrinksSpiritsLiqueur": View(key="tillDrinksSpiritsLiqueur", image_path="Till Images/tillDrinksSpiritsLiqueur.jpg", name="Till Submenu: Spirits Liqueur", neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None}),
    "tillDrinksSpiritsShots": View(key="tillDrinksSpiritsShots", image_path="Till Images/tillDrinksSpiritsShots.jpg", name="Till Submenu: Spirits Shots", neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None}),
    "tillDrinksSpiritsWhiskey": View(key="tillDrinksSpiritsWhiskey", image_path="Till Images/tillDrinksSpiritsWhiskey.jpg", name="Till Submenu: Spirits Whiskey", neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None}),
    "tillDrinksWineRed175": View(key="tillDrinksWineRed175", image_path="Till Images/tillDrinksWineRed175.jpg", name="Till Submenu: Wine Red 175", neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None}),
    "tillDrinksWineRed250": View(key="tillDrinksWineRed250", image_path="Till Images/tillDrinksWineRed250.jpg", name="Till Submenu: Wine Red 250", neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None}),
    "tillDrinksWineWhite175": View(key="tillDrinksWineWhite175", image_path="Till Images/tillDrinksWineWhite175.jpg", name="Till Submenu: Wine White 175", neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None}),
    "tillDrinksWineWhite250": View(key="tillDrinksWineWhite250", image_path="Till Images/tillDrinksWineWhite250.jpg", name="Till Submenu: Wine White 250", neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None}),
    "tillDrinksWineRose175": View(key="tillDrinksWineRose175", image_path="Till Images/tillDrinksWineRose175.jpg", name="Till Submenu: Wine Rose 175", neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None}),
    "tillDrinksWineRose250": View(key="tillDrinksWineRose250", image_path="Till Images/tillDrinksWineRose250.jpg", name="Till Submenu: Wine Rose 250", neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None}),
    "tillFoodBreakfast": View(key="tillFoodBreakfast", image_path="Till Images/tillFoodBreakfast.jpg", name="Till Food: Breakfast", neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None}),
    "tillFoodDaytime": View(key="tillFoodDaytime", image_path="Till Images/tillFoodDaytime.jpg", name="Till Food: Daytime", neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None}),
    # Customer screen - W from any till screen; S returns to the till you came from.
    # No left/right/turn/crouch from here.
    # Blank for now with placeholder text box for customer demands.
    "customer": View(
        key="customer",
        image_path=None,  # special blank screen, drawn manually
        name="Customer",
        neighbors={
            "left": None,
            "right": None,
            "forward": None,
            "back": "tillDrinks",
            "turn_left": None,
            "turn_right": None,
            "crouch": None,
            "stand": None,
        },
    ),
}

# Keys to preload (order doesn't matter much for graph navigation)
VIEW_ORDER = list(VIEWS.keys())

# Auto-register any additional till* camelCase views from Till Images (supports new images added by user for switch: )
try:
    till_img_dir = _get_bar_images_root() / "Till Images"
    if till_img_dir.exists():
        for img_file in sorted(till_img_dir.glob("till*.jpg")):
            key = img_file.stem
            if key not in VIEWS:
                VIEWS[key] = View(
                    key=key,
                    image_path=f"Till Images/{img_file.name}",
                    name=f"Till View: {key}",
                    neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
                )
                VIEW_ORDER.append(key)  # for completeness, though order may not be perfect
except Exception:
    pass  # if paths not ready or no dir, skip auto add (will fail load later if switched to)

# (TILL_BAR_TABS and TILL_FOOD_TABS removed - all buttons now come from the editor tool via JSON)

# Back button area for submenu screens (top right, approximate)
TILL_SUB_BACK_RECT = (2750, 60, 360, 110)

# Default till home + bar position when leaving any till screen with S.
TILL_HOME = "tillDrinks"
TILL_BAR_EXIT = "1W1"

# (Persistent top-left BAR/FOOD navigation buttons have been removed.
# They are now expected to be added by the user via the till_button_tool
# using "switch:tillDrinks" / "switch:tillFood" etc. actions.)

# Customer screen UI buttons + boxes (screen coordinates)
# These are now *recomputed every frame* from the current window size (see run_demo)
# for fullscreen / resizable support. The values below are only "base" / documentation.
# (Dynamic right column under sent box, left placed box, etc.)
# Customer screen layout (recomputed each frame in run_demo; defaults below).
PLACED_ITEMS_BOX = (20, 50, 300, 300)
SENT_ITEMS_BOX = (960, 50, 300, 300)
GRADE_AGAIN_RECT = (20, 370, 300, 38)
GRADE_HARD_RECT  = (20, 412, 300, 38)
GRADE_GOOD_RECT  = (20, 454, 300, 38)
GRADE_EASY_RECT  = (20, 496, 300, 38)
RESET_BUTTON_RECT = (20, 546, 300, 40)
RESET_TILL_BUTTON_RECT = (960, 365, 300, 40)
FINISH_BUTTON_RECT = (960, 415, 300, 40)

# Possible customer demands are now loaded dynamically from NeuroMods/Bar/BarGame.nm
# (generated by src/bar/genOrders.py).
#
# Only items that have BOTH a take:/pour: button (to acquire the item) AND an order: button
# (to send it) are included (with special rule for food items).
# BarGame.nm is content,source CSV (type=bar, cue, response per row).
# This list (of dicts) is used for (weighted) practice-mode (non-review) customer
# demand generation via load_potential_orders() above.
# Weights: food=1.0, side=0.25, extra=0.25, other=1.0, wine=1.0, beer=1.0
# (beer bases emptyGlass excluded; *Full/*Poured beer and *25/*50/*125 thimble wines included as beer/wine)
#
# Run the generator script after editing buttons in the till editor.
POSSIBLE_DEMANDS = load_potential_orders()  # list of dicts: key, Display, type, weight
DEMAND_LOOKUP = {d["key"]: d for d in POSSIBLE_DEMANDS if isinstance(d, dict) and d.get("key")}


def format_demand(demand: str) -> str:
    """Return the customer demand line for a key (from lookup or computed)."""
    return format_customer_demand(demand, lookup=DEMAND_LOOKUP)


def format_item_label(item_key: str) -> str:
    """Placed/sent box label: customer wording without a/an (not raw key)."""
    return format_counter_item(item_key, lookup=DEMAND_LOOKUP)


def _beer_glass_base_key(demand: str) -> str | None:
    if demand in BEER_GLASS_BASES:
        return demand
    for suf in ("Poured", "Full", "Half"):
        if demand.endswith(suf):
            base = demand[: -len(suf)]
            if base in BEER_GLASS_BASES:
                return base
    return None


def _is_beer_demand(demand: str, beer_glass_to_drink: dict) -> bool:
    if demand in beer_glass_to_drink:
        return True
    meta = DEMAND_LOOKUP.get(demand, {})
    return meta.get("type") == "beer" or _beer_glass_base_key(demand) is not None


def _demand_sent_only(demand: str, burger_demands: set) -> bool:
    if demand in burger_demands:
        return True
    meta = DEMAND_LOOKUP.get(demand, {})
    if meta.get("type") in ("food", "side", "extra"):
        return True
    return str(demand).lower().startswith("food")


def _check_demand_fulfilled(
    demand: str,
    placed: list,
    sent_orders: list,
    beer_glass_to_drink: dict,
    burger_demands: set,
) -> tuple[bool, str, str, str]:
    """Return (ok, rule, expected_desc, got_desc). Order of placed/sent does not matter."""
    placed_set = set(placed)
    sent_set = set(sent_orders)

    if _is_beer_demand(demand, beer_glass_to_drink):
        base = _beer_glass_base_key(demand) or demand
        drink = beer_glass_to_drink.get(demand) or beer_glass_to_drink.get(base, "")
        glass_ok = demand in placed_set or base in placed_set
        sent_ok = demand in sent_set or bool(drink and drink in sent_set)
        ok = glass_ok and sent_ok
        need_send = demand if demand in sent_set or demand in beer_glass_to_drink else (drink or demand)
        expected = f"place {base} + send {need_send}"
        got_placed = [x for x in placed if x in (demand, base)]
        got_sent = [x for x in sent_orders if x == demand or (drink and x == drink)]
        got = f"placed [{', '.join(got_placed) or '—'}]; sent [{', '.join(got_sent) or '—'}]"
        return ok, "beer", expected, got

    if _demand_sent_only(demand, burger_demands):
        ok = demand in sent_set
        expected = f"send {demand}"
        got_sent = [x for x in sent_orders if x == demand]
        got = f"sent [{', '.join(got_sent) or '—'}]"
        return ok, "sent", expected, got

    ok = demand in placed_set
    expected = f"place {demand}"
    got_placed = [x for x in placed if x == demand]
    got = f"placed [{', '.join(got_placed) or '—'}]"
    return ok, "placed", expected, got


def _items_accounted_for(
    current_demands: list[str],
    placed: list,
    sent_orders: list,
    beer_glass_to_drink: dict,
    burger_demands: set,
) -> tuple[set[str], set[str]]:
    """Placed/sent item ids that count toward a demand (not extras)."""
    used_placed: set[str] = set()
    used_sent: set[str] = set()
    for demand in current_demands:
        if _is_beer_demand(demand, beer_glass_to_drink):
            base = _beer_glass_base_key(demand) or demand
            drink = beer_glass_to_drink.get(demand) or beer_glass_to_drink.get(base, "")
            for item in placed:
                if item in (demand, base):
                    used_placed.add(item)
            for item in sent_orders:
                if item == demand or (drink and item == drink):
                    used_sent.add(item)
        elif _demand_sent_only(demand, burger_demands):
            if demand in sent_orders:
                used_sent.add(demand)
        else:
            for item in placed:
                if item == demand:
                    used_placed.add(item)
    return used_placed, used_sent


def _score_customer_demands(
    current_demands: list[str],
    placed: list,
    sent_orders: list,
    beer_glass_to_drink: dict,
    burger_demands: set,
) -> tuple[int, int, set[str], list[str]]:
    """Score finish; return success count, total, succeeded set, report lines."""
    total = len(current_demands)
    success = 0
    succeeded: set[str] = set()
    lines: list[str] = []
    for demand in current_demands:
        ok, _rule, _expected, _got = _check_demand_fulfilled(
            demand, placed, sent_orders, beer_glass_to_drink, burger_demands)
        if ok:
            lines.append(f"OK {demand}")
            success += 1
            succeeded.add(demand)
        else:
            lines.append(f"MISSING {demand}")

    used_placed, used_sent = _items_accounted_for(
        current_demands, placed, sent_orders, beer_glass_to_drink, burger_demands)
    seen_extra: set[str] = set()
    for item in placed:
        if item not in used_placed and item not in seen_extra:
            lines.append(f"EXTRA {item}")
            seen_extra.add(item)
    for item in sent_orders:
        if item not in used_sent and item not in seen_extra:
            lines.append(f"EXTRA {item}")
            seen_extra.add(item)

    header = f"{success}/{total} orders successful"
    return success, total, succeeded, [header, ""] + lines


GRADE_LABELS: dict[int, str] = {1: "Again", 2: "Hard", 3: "Good", 4: "Easy"}
GRADE_OPTIONS: list[tuple[int, str]] = [(g, GRADE_LABELS[g]) for g in (1, 2, 3, 4)]
# FSRS-style: Again → Hard → Good → Easy = red → orange → blue → green
GRADE_COLORS: dict[int, tuple[int, int, int]] = {
    1: (178, 48, 48),
    2: (204, 118, 42),
    3: (48, 102, 198),
    4: (48, 158, 82),
}


def grade_label(grade: int | None) -> str:
    if grade is None:
        return ""
    return GRADE_LABELS.get(grade, str(grade))


def _grade_fill_color(
    grade: int,
    *,
    selected: bool = False,
    hover_blend: float = 0.0,
) -> tuple[int, int, int]:
    base = GRADE_COLORS.get(grade, (55, 55, 55))
    if selected:
        base = tuple(min(255, c + 40) for c in base)
    elif hover_blend > 0:
        base = ui_theme._shift(base, int(10 * hover_blend))
    return base


def _draw_photo_button(
    screen,
    sx: int,
    sy: int,
    sw: int,
    sh: int,
    btn: dict,
    small_font,
    *,
    hover_blend: float = 0.0,
    bar_view: bool,
) -> None:
    """Draw an editor-defined photo hotspot; bar views get hover polish."""
    color_name = btn.get("color", "blue")
    rgb = _BUTTON_COLORS.get(color_name, (0, 0, 0))
    blend = hover_blend if bar_view else 0.0
    if blend > 0:
        grow = 1.0 + blend * ui_theme.PHOTO_HOVER_GROW_AMOUNT
        sx, sy, sw, sh = ui_theme.AIscaleRectAroundCenter((sx, sy, sw, sh), grow)

    radius = max(2, min(6, sw // 2, sh // 2))
    text_color = None

    if color_name == "transparent border":
        border_alpha = int(190 + 20 * blend)
        border_col = (70, 70, 75, border_alpha)
        if blend > 0:
            border_col = (*ui_theme.YELLOW_BORDER, border_alpha)
        border_surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
        pygame.draw.rect(
            border_surf, border_col, (0, 0, sw, sh), width=2, border_radius=radius)
        screen.blit(border_surf, (sx, sy))
    elif color_name == "transparent black":
        fill_alpha = int(128 + 20 * blend)
        s = pygame.Surface((sw, sh), pygame.SRCALPHA)
        pygame.draw.rect(s, (0, 0, 0, fill_alpha), (0, 0, sw, sh), border_radius=radius)
        screen.blit(s, (sx, sy))
        text_color = (255, 255, 255)
    else:
        pygame.draw.rect(screen, rgb, (sx, sy, sw, sh), border_radius=radius)
        if blend > 0:
            s = pygame.Surface((sw, sh), pygame.SRCALPHA)
            hover_rgb = tuple(min(255, int(c + 25 * blend)) for c in rgb)
            overlay_alpha = int(200 * blend)
            pygame.draw.rect(
                s, (*hover_rgb, overlay_alpha), (0, 0, sw, sh), border_radius=radius)
            screen.blit(s, (sx, sy))
        text_color = (0, 0, 0) if color_name != "black" else (255, 255, 255)

    if text_color is not None:
        label_surf = small_font.render(btn.get("label", "?"), True, text_color)
        text_x = sx + (sw - label_surf.get_width()) // 2
        text_y = sy + (sh - label_surf.get_height()) // 2
        screen.blit(label_surf, (text_x, text_y))


def _draw_grade_button(
    screen,
    rect: tuple[int, int, int, int],
    grade: int,
    label: str,
    font,
    *,
    selected: bool = False,
    hover_blend: float = 0.0,
) -> None:
    """Draw a single FSRS-coloured grade button (fill + border + centred label)."""
    fill = _grade_fill_color(grade, selected=selected, hover_blend=hover_blend)
    pygame.draw.rect(screen, fill, rect, border_radius=ui_theme.BTN_RADIUS)
    border = tuple(max(0, c - 50) for c in fill)
    pygame.draw.rect(screen, border, rect, 1, border_radius=ui_theme.BTN_RADIUS)
    text_col = (255, 255, 255) if not selected else (255, 255, 220)
    gtxt = font.render(label, True, text_col)
    gx = rect[0] + (rect[2] - gtxt.get_width()) // 2
    gy = rect[1] + (rect[3] - gtxt.get_height()) // 2
    screen.blit(gtxt, (gx, gy))


def _grade_for_fulfilled_demand(
    demand: str,
    placed_grades: dict,
    sent_grades: dict,
    beer_glass_to_drink: dict,
) -> int:
    """User-assigned grade for a correctly fulfilled demand (default Good)."""
    if demand in placed_grades:
        return placed_grades[demand]
    if demand in sent_grades:
        return sent_grades[demand]
    drink = beer_glass_to_drink.get(demand)
    if drink and drink in sent_grades:
        return sent_grades[drink]
    return 3


def _send_grade_popup_layout(
    win_w: int,
    win_h: int,
    n_items: int,
) -> tuple[int, int, int, int, list[tuple[tuple[int, int, int, int], int]]]:
    """Centre modal geometry and clickable grade rows (autocomplete-style)."""
    panel_w = 320
    row_h = 28
    header_h = 36
    shown = min(n_items, 6)
    items_h = shown * 18 + 8
    if n_items > 6:
        items_h += 14
    opts_h = len(GRADE_OPTIONS) * row_h + 8
    footer_h = 20
    panel_h = header_h + items_h + opts_h + footer_h + 16
    panel_x = (win_w - panel_w) // 2
    panel_y = (win_h - panel_h) // 2

    y = panel_y + header_h + 18 + shown * 16
    if n_items > 6:
        y += 14
    y += 28

    option_rects: list[tuple[tuple[int, int, int, int], int]] = []
    for grade, _label in GRADE_OPTIONS:
        opt_rect = (panel_x + 12, y, panel_w - 24, row_h - 4)
        option_rects.append((opt_rect, grade))
        y += row_h
    return panel_x, panel_y, panel_w, panel_h, option_rects


def _draw_send_grade_popup(
    screen,
    font,
    small_font,
    win_w: int,
    win_h: int,
    pending_items: list[str],
    selection_index: int,
    *,
    mx: int,
    my: int,
    hover_grow: ui_theme.AIHoverGrow,
    dt_seconds: float,
) -> None:
    """Draw dim overlay + centre grade picker after send_order."""
    ui_theme.draw_modal_overlay(screen, win_w, win_h)

    panel_x, panel_y, panel_w, panel_h, option_rects = _send_grade_popup_layout(
        win_w, win_h, len(pending_items))

    ui_theme.draw_panel(
        screen,
        (panel_x, panel_y, panel_w, panel_h),
        fill=ui_theme.MODAL_FILL,
        border=ui_theme.MODAL_BORDER,
    )

    title = font.render("Send order — choose grade", True, ui_theme.PANEL_HEADER)
    screen.blit(title, (panel_x + 12, panel_y + 10))

    y = panel_y + 36
    screen.blit(small_font.render("Items:", True, ui_theme.PANEL_MUTED), (panel_x + 12, y))
    y += 18
    for item in pending_items[:6]:
        line = f"• {format_item_label(item)}"
        if small_font.size(line)[0] > panel_w - 28:
            while line and small_font.size(line + "…")[0] > panel_w - 28:
                line = line[:-1]
            line += "…"
        screen.blit(small_font.render(line, True, ui_theme.PANEL_BODY), (panel_x + 16, y))
        y += 16
    if len(pending_items) > 6:
        extra = small_font.render(f"  +{len(pending_items) - 6} more", True, ui_theme.PANEL_HINT)
        screen.blit(extra, (panel_x + 16, y))

    y = option_rects[0][0][1] - 20
    screen.blit(
        small_font.render("Grade (↑/↓  Enter  Esc=cancel):", True, ui_theme.PANEL_MUTED),
        (panel_x + 12, y),
    )

    for ii, (opt_rect, grade) in enumerate(option_rects):
        opt_hover = ui_theme.point_in_rect(mx, my, opt_rect)
        opt_blend = hover_grow.update(f"send_grade:{grade}", opt_hover, dt_seconds)
        draw_rect = ui_theme.AIscaleRectAroundCenter(
            opt_rect, hover_grow.scale(opt_blend))
        _draw_grade_button(
            screen,
            draw_rect,
            grade,
            GRADE_LABELS[grade],
            small_font,
            selected=(ii == selection_index),
            hover_blend=opt_blend,
        )

    hint = small_font.render("Click a grade to send", True, ui_theme.PANEL_HINT)
    screen.blit(hint, (panel_x + 12, panel_y + panel_h - 22))


def _wrap_text_lines(font, text: str, max_width: int) -> list[str]:
    """Word-wrap a single paragraph to fit max_width (pixels)."""
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if font.size(trial)[0] <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _wrap_bullet_lines(font, text: str, max_width: int, bullet: str = "• ") -> list[str]:
    """Wrap a bullet item; continuation lines are indented under the bullet."""
    indent = " " * len(bullet)
    inner_w = max(40, max_width - font.size(bullet)[0])
    body_lines = _wrap_text_lines(font, text, inner_w)
    if not body_lines:
        return [bullet]
    wrapped = [bullet + body_lines[0]]
    wrapped.extend(indent + line for line in body_lines[1:])
    return wrapped


def _customer_demands_content_height(
    *,
    small_font,
    console_font,
    text_width: int,
    demand_keys: list[str],
    report_lines: list[str],
    showing_report: bool,
    line_h: int = 18,
    pad_y: int = 12,
) -> int:
    """Pixel height needed to show all demands-panel lines without clipping."""
    if showing_report and report_lines:
        lines: list[str] = []
        for line in report_lines:
            lines.extend(_wrap_text_lines(console_font, line, text_width))
        return pad_y * 2 + line_h * len(lines)
    formatted = [format_demand(k) for k in demand_keys]
    return pad_y * 2 + line_h * len(
        _build_customer_demands_lines(small_font, formatted, text_width))


def _build_customer_demands_lines(font, formatted_demands: list[str], text_width: int) -> list[str]:
    """Build wrapped line list for the customer demands panel."""
    help_lines = [
        "Left-click take buttons (on position views) to put glass in left hand; right-click for right hand.",
        "On customer: click a grade button to place from hand (prefers right hand, then left) + rate recall.",
    ]
    lines: list[str] = []
    lines.extend(_wrap_text_lines(font, "Customer demands:", text_width))
    lines.append("")
    for demand in formatted_demands:
        lines.extend(_wrap_bullet_lines(font, demand, text_width))
    lines.append("")
    for paragraph in help_lines:
        lines.extend(_wrap_text_lines(font, paragraph, text_width))
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


# (TILL_FOOD_TABS removed - all buttons now come from the editor tool via JSON)

# (The old TILL_PHOTO_BUTTONS list has been removed.
# Use the drag-and-drop tool src/bar/till_button_tool.py to create/edit buttons.
# It saves to NeuroMods/Bar/till_buttons.json which is loaded automatically.)

# (Old per-screen item lists removed - use the in-house editor tool instead)
# Load buttons created with the drag-and-drop tool (NeuroMods/Bar/till_buttons.json)
import json as _json
from pathlib import Path as _Path

def _load_till_photo_buttons():
    try:
        p = _Path(__file__).resolve().parent.parent.parent / "NeuroMods" / "Bar" / "till_buttons.json"
        if p.exists():
            with open(p, "r") as f:
                return _json.load(f)
    except Exception as e:
        print("Warning: could not load till_buttons.json:", e)
    return {}

TILL_PHOTO_BUTTON_DATA = _load_till_photo_buttons()

# Color map for the editor tool (must match the one in till_button_tool.py)
_BUTTON_COLORS = {
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
    "black": (0, 0, 0),
    "transparent black": (0, 0, 0),
    "transparent border": (0, 0, 0),  # completely transparent fill + opaque black border only; no text/label drawn (for pure hotspots)
}


def get_view(key: str) -> View:
    if key not in VIEWS:
        raise KeyError(f"Unknown view key: {key}")
    return VIEWS[key]


def is_south_facing(key: str) -> bool:
    """Return True if this view is facing south.

    When facing south the player's left = east on the bar, right = west.
    This is used to make A/D keys relative to the player's orientation
    instead of always map-absolute.
    Supports old _s keys and new SpotDirHeight naming (e.g. 3S1).
    """
    if len(key) >= 2 and key[1] in ("S", "s"):
        return True
    return "_s" in key


def try_height_toggle(key: str):
    """Return the target key for a height change (crouch or stand) if available.

    This allows a single button (Ctrl) to toggle between standing and crouching
    when a relevant transition exists for the current view.
    Tries crouch first, then stand.
    """
    view = get_view(key)
    for action in ("crouch", "stand"):
        target = view.go(action)
        if target:
            return target
    return None


def _turn_key(key: str, clockwise: bool = True) -> Optional[str]:
    """Compute logical turn key for the current facing (for E/W/N/S)."""
    if len(key) != 3 or not key[0].isdigit():
        return None
    spot = key[0]
    d = key[1].upper()
    h = key[2]
    cycle = "NESW"
    if d not in cycle:
        return None
    idx = cycle.index(d)
    delta = 1 if clockwise else -1
    nd = cycle[(idx + delta) % 4]
    tkey = f"{spot}{nd}{h}"
    if tkey in VIEWS:
        return tkey
    # fallback to other height at turned direction
    other_h = "0" if h == "1" else "1"
    tkey2 = f"{spot}{nd}{other_h}"
    if tkey2 in VIEWS:
        return tkey2
    return None


# ---------------------------------------------------------------------------
# Pygame helpers
# ---------------------------------------------------------------------------

def load_image_surface(view: View, images_dir: Path):
    """Load and convert the jpg for fast blitting. Caching is done by caller."""
    global pygame
    if pygame is None:
        import pygame as _pygame
        pygame = _pygame
    full_path = images_dir / view.image_path
    if not full_path.exists():
        raise FileNotFoundError(f"Missing image: {full_path}")
    # .convert() is important for performance
    return pygame.image.load(str(full_path)).convert()


def _blit_loading_preview(screen, surface, win_w: int, win_h: int) -> int:
    """Draw the last loaded view as a small centred thumbnail; return bottom y."""
    max_w = min(420, int(win_w * 0.38))
    max_h = min(236, int(win_h * 0.32))
    src_w, src_h = surface.get_size()
    scale = min(max_w / src_w, max_h / src_h)
    tw = max(1, int(src_w * scale))
    th = max(1, int(src_h * scale))
    thumb = pygame.transform.smoothscale(surface, (tw, th))
    x = (win_w - tw) // 2
    y = (win_h - th) // 2 - 24
    pad = 3
    pygame.draw.rect(
        screen,
        ui_theme.PANEL_FILL,
        (x - pad, y - pad, tw + pad * 2, th + pad * 2),
        border_radius=6,
    )
    pygame.draw.rect(
        screen,
        ui_theme.PANEL_BORDER,
        (x - pad, y - pad, tw + pad * 2, th + pad * 2),
        2,
        border_radius=6,
    )
    screen.blit(thumb, (x, y))
    return y + th + 20


def scale_and_center(
    surface,
    target_size: tuple[int, int],
):
    """Scale preserving aspect. Returns (scaled_surface, (blit_x, blit_y))."""
    global pygame
    if pygame is None:
        import pygame as _pygame
        pygame = _pygame

    src_w, src_h = surface.get_size()
    tgt_w, tgt_h = target_size

    scale = min(tgt_w / src_w, tgt_h / src_h)
    new_w = max(1, int(src_w * scale))
    new_h = max(1, int(src_h * scale))

    scaled = pygame.transform.smoothscale(surface, (new_w, new_h))

    x = (tgt_w - new_w) // 2
    y = (tgt_h - new_h) // 2
    return scaled, (x, y)


def screen_to_image_coords(
    screen_x: int,
    screen_y: int,
    blit_x: int,
    blit_y: int,
    scaled_w: int,
    scaled_h: int,
    original_w: int,
    original_h: int,
):
    """
    Convert a click on the window (screen_x, screen_y) back to
    coordinates in the original high-res photograph.
    """
    global pygame
    if pygame is None:
        import pygame as _pygame
        pygame = _pygame

    if not (blit_x <= screen_x < blit_x + scaled_w and blit_y <= screen_y < blit_y + scaled_h):
        # Clicked on the letterbox / outside the photo
        return (-1, -1)

    rel_x = screen_x - blit_x
    rel_y = screen_y - blit_y

    ix = int(rel_x / scaled_w * original_w)
    iy = int(rel_y / scaled_h * original_h)
    return ix, iy


# ---------------------------------------------------------------------------
# Display (maximized window with title bar; Wayland-friendly)
# ---------------------------------------------------------------------------

_WINDOWED_SIZE = (1280, 720)


def _desktop_size(pygame_module) -> tuple[int, int]:
    info = pygame_module.display.Info()
    w, h = info.current_w, info.current_h
    if w > 0 and h > 0:
        return w, h
    return _WINDOWED_SIZE


def AIgetSdlWindow(pygame_module):
    """Return the SDL window for the active display surface, if available."""
    try:
        from pygame._sdl2 import Window

        return Window.from_display_module()
    except Exception:
        return None


def _pump_display_resize(pygame_module, *, attempts: int = 8) -> None:
    """Let the window manager apply maximize/restore before we read get_size()."""
    pygame_module.event.pump()
    for _ in range(attempts):
        pygame_module.time.wait(16)
        pygame_module.event.pump()


def AIsyncDisplaySurface(pygame_module, surf) -> object:
    """Recreate the drawable surface at the window's current size.

    After SDL_Window.maximize() on KDE/Wayland the window can report a larger
    size while the backing framebuffer is still the old dimensions — the next
    blit/flip then segfaults. Always call set_mode again with the reported size.
    """
    got_w, got_h = surf.get_size()
    if got_w <= 0 or got_h <= 0:
        return surf
    try:
        return pygame_module.display.set_mode(
            (got_w, got_h), pygame_module.RESIZABLE)
    except pygame_module.error:
        return surf


def AIsetGameDisplay(pygame_module, *, fullscreen: bool) -> tuple[object, bool, str]:
    """Open windowed or maximized display. Returns (surface, is_fullscreen, mode_label)."""
    if not fullscreen:
        surf = pygame_module.display.set_mode(_WINDOWED_SIZE, pygame_module.RESIZABLE)
        sdl_window = AIgetSdlWindow(pygame_module)
        if sdl_window is not None:
            try:
                sdl_window.restore()
            except Exception:
                pass
        _pump_display_resize(pygame_module)
        surf = AIsyncDisplaySurface(pygame_module, surf)
        got_w, got_h = surf.get_size()
        return surf, False, f"windowed {got_w}x{got_h}"

    # Create a normal decorated window, then ask the WM to maximize it. This is
    # more reliable on KDE/Wayland than SDL_WINDOW_MAXIMIZED alone at creation.
    surf = pygame_module.display.set_mode(_WINDOWED_SIZE, pygame_module.RESIZABLE)
    sdl_window = AIgetSdlWindow(pygame_module)
    if sdl_window is not None:
        try:
            sdl_window.maximize()
            _pump_display_resize(pygame_module)
            got_w, got_h = surf.get_size()
            if got_w > _WINDOWED_SIZE[0] or got_h > _WINDOWED_SIZE[1]:
                surf = AIsyncDisplaySurface(pygame_module, surf)
                got_w, got_h = surf.get_size()
                return surf, True, f"maximized {got_w}x{got_h}"
        except Exception:
            pass

    maximized_flags = pygame_module.RESIZABLE | pygame_module.WINDOWMAXIMIZED
    try:
        surf = pygame_module.display.set_mode(_WINDOWED_SIZE, maximized_flags)
        _pump_display_resize(pygame_module)
        got_w, got_h = surf.get_size()
        if got_w > _WINDOWED_SIZE[0] or got_h > _WINDOWED_SIZE[1]:
            surf = AIsyncDisplaySurface(pygame_module, surf)
            got_w, got_h = surf.get_size()
            return surf, True, f"maximized {got_w}x{got_h}"
    except pygame_module.error:
        pass

    w, h = _desktop_size(pygame_module)
    try:
        surf = pygame_module.display.set_mode((w, h), pygame_module.RESIZABLE)
        got_w, got_h = surf.get_size()
        return surf, True, f"large window {got_w}x{got_h}"
    except pygame_module.error:
        pass

    surf = pygame_module.display.set_mode(_WINDOWED_SIZE, pygame_module.RESIZABLE)
    return surf, False, f"windowed {_WINDOWED_SIZE[0]}x{_WINDOWED_SIZE[1]} (maximized unavailable)"


# ---------------------------------------------------------------------------
# The actual demo
# ---------------------------------------------------------------------------

def run_demo() -> None:
    """Launch the interactive bar explorer demo."""
    global pygame, _review_mode, _due_map, _practice_mode
    if pygame is None:
        import pygame as _pygame
        pygame = _pygame

    images_dir = _get_bar_images_root()
    print(f"Using images from: {images_dir} (Bar Images/ + Till Images/)")

    # Order system for till interactions (bar drinks + food items)
    orders = []

    # Hand state for take actions (e.g. holding glasses). Left-click take: puts in left_hand,
    # right-click take: puts in right_hand. PLACE grade buttons empty both hands onto the counter.
    left_hand = None
    right_hand = None

    # Placed items on the customer counter (persists across leaving the screen)
    placed = []

    # User-chosen grades (1-4) for placed items. Used for FSRS updates on "placed" demands in review mode.
    placed_grades = {}

    # Sent orders from the till (food/drink orders sent via send button)
    sent_orders = []

    # User-chosen grades (1-4) for sent items (from the split send-grade buttons on till screens).
    # Used for FSRS on correctly fulfilled sent/placed demands in review mode.
    sent_grades = {}

    # Current customer demands (auto-generated, 3-6 items).
    # In review mode this will draw from remaining due bar cards until exhausted.
    current_demands = _sample_next_demands()

    # After FINISH: report replaces demands panel until CONTINUE is pressed.
    finish_report_lines: list[str] = []
    customer_awaiting_continue = False

    # Send-grade popup (after send_order till button)
    pending_send_items: list[str] | None = None
    send_popup_selection = 2  # default highlight: Good
    send_popup_option_rects: list[tuple[tuple[int, int, int, int], int]] = []

    # Mapping for beer glass demands to the drink name sent from till
    # Keys updated to new take: naming scheme (see normalize in till_button_tool)
    BEER_GLASS_TO_DRINK = {
        "stellaGlass": "Stella",
        "morretiGlass": "Moretti",
        "madriGlass": "Madri",
        "coorsGlass": "Coors",
        "carlingGlass": "Carling",
        "guinessGlass": "Guiness",
        "doombarGlass": "Doom Bar",
        "cruzcampoGlass": "Cruzcampo",
        "morettiGlass": "Moretti",
        # Full / Poured / Half variants (per genOrders: these are type 'beer')
        "madriGlassFull": "Madri",
        "madriGlassPoured": "Madri",
        "madriGlassHalf": "Madri",
        "guinessGlassFull": "Guiness",
        "guinessGlassPoured": "Guiness",
        "guinessGlassHalf": "Guiness",
        "carlingGlassFull": "Carling",
        "carlingGlassPoured": "Carling",
        "carlingGlassHalf": "Carling",
        "coorsGlassFull": "Coors",
        "coorsGlassPoured": "Coors",
        "coorsGlassHalf": "Coors",
        "doombarGlassFull": "Doom Bar",
        "doombarGlassPoured": "Doom Bar",
        "doombarGlassHalf": "Doom Bar",
        "cruzcampoGlassFull": "Cruzcampo",
        "morettiGlassFull": "Moretti",
        "morettiGlassPoured": "Moretti",
        "morettiGlassHalf": "Moretti",
        "strongbowGlassFull": "Strongbow",
        # legacy snake for compat with older demands/buttons
        "Stella_glass": "Stella",
        "Morreti_glass": "Moretti",
        "Madri_glass": "Madri",
        "Coors_glass": "Coors",
        "Carling_glass": "Carling",
    }

    # Burger items that are sent from food sub-menus
    BURGER_DEMANDS = {"BGR_Big_Stack", "BGR_Bombay", "BGR_Chs_Bcn", "BGR_Korean", "BGR_Korean_grilled", "BGR_Vegan"}

    # Mapping for new send button actions (split Send area into Send label + 4 grade buttons)
    # The user will create these via the till_button_tool on the till screen images.
    # When clicked, sends the current orders AND assigns the grade to all sent items.
    SEND_GRADE_MAP = {
        "sendAgain": 1,
        "sendHard": 2,
        "sendGood": 3,
        "sendEasy": 4,
        # support common capitalizations
        "SendAgain": 1,
        "SendHard": 2,
        "SendGood": 3,
        "SendEasy": 4,
        "sendagain": 1,
        "sendhard": 2,
        "sendgood": 3,
        "sendeasy": 4,
    }

    # Pour actions (multi-stage feature).
    # Button action in the editor tool: "pour:BASE"  (e.g. "pour:madriGlass")
    # Click *with the hand holding the item*:
    #   left-click  → affects left_hand
    #   right-click → affects right_hand
    # BASE → BASEHalf (first click)
    # BASEHalf → BASEFull (second click)
    # BASEFull / wrong item / other hand click → nothing
    #
    # Applies to all pour: actions. Buttons are created as "pour:BASE" (not pour:BASEPoured).
    POUR_TRANSFORMS = {}  # (legacy, not used by current pour logic)

    # Crafting actions (new feature).
    # Button action in the editor tool: "crafting:RESULT"
    # When clicked (left click) while holding exactly the required pair of items (one in left hand, one in right hand),
    # both items are removed and the RESULT is placed in the right hand.
    # Recipes are defined as frozenset (order of hands doesn't matter).
    # Add more entries as you create "crafting:..." buttons via the item icon mapper tool or manually.
    # Example recipes (uncomment and extend as needed):
    #     frozenset({"boston_shaker_tin", "tails_pina_colada"}): "mixed_pina_colada",
    #     frozenset({"lemon_slice", "lime_slice"}): "citrus_mix",
    CRAFT_RECIPES = {
        # result: frozenset of the two input items (order-independent)
        # Example (add real ones based on your bar recipes):
        # frozenset({"boston_shaker_tin", "tails_pina_colada"}): "shaken_pina_colada",
    }

    def _apply_thimble(it, num):
        base, _ = strip_thimble_suffix(str(it))
        return base + str(num)

    # Helpful startup info for the current layout
    print("\n=== Current known layout (new Bar Images/ SpotDirH photos) ===")
    print("Spots 1(west)-7(east). Keys: e.g. 1N1=spot1 North stand, 7S0=spot7 South crouch.")
    print(font_status())
    print(f"Session mode: {_session_mode_label()}")
    if not _review_mode:
        print("  (Practice — demands from NeuroMods/Bar/BarGame.nm, no FSRS updates)")
    elif _practice_mode:
        print("  (Practice — due bar cards finished; still no FSRS updates)")
    else:
        print(f"  (Review — {len(_due_map)} due bar card(s) in queue)")
    print("Till at west of spot 1. Customer forward from tillDrinks.")
    print()
    print("Controls:")
    print("  W / S (or Up/Down) : forward / back (along facing, esp. useful for E/W facings)")
    print("  A / D              : left / right from player's perspective (for N/S: along bar)")
    print("  Left/Right arrows  : absolute west / east on the bar")
    print("  Q / E              : turn left / turn right")
    print("  Ctrl (or C)        : toggle between crouch and stand (when relevant for the current view)")
    print("  Top BAR/FOOD + photo buttons : (add your own via the tool with switch: actions; all other photo buttons come from JSON)")
    print("  To visually design buttons   : run  python -m src.bar.till_button_tool")
    print("  To map items to icons        : run  python -m src.bar.item_icon_tool")
    print("  To position till on frame    : run  python -m src.bar.till_viewport_tool")
    print("  To position customer portrait: run  python -m src.bar.customer_viewport_tool")
    print("  pour: buttons                : click with the hand holding BASE/BASEHalf on 'pour:BASE' (left-click=left hand, right-click=right) to progress to Half then Full")
    print("  take: spirit (with shot glass): shotsGlass + take:spirit → spiritSingle; same spirit again → spiritDouble; then no more")
    print("  crafting: buttons            : left-click while holding the exact pair of items for the result (in either hand)  [predefined recipes]")
    print("  craft: buttons               : left-click while holding two measured wines/spirits of the same base (e.g. redXXX25 + redXXX125) → combined amount in right hand")
    print("  thimble: buttons             : click with hand holding wine or spirit on thimble:25/50/125 (not softs/cans/beer/crisps/kids drinks)")
    print("  opener: buttons              : click with hand holding a bottle (j20, *Zero, softs, etc.) → *Opened in that hand")
    print("  void: buttons                : left-click to remove the most recently added order item")
    print("  Buttons are loaded from      : NeuroMods/Bar/till_buttons.json")
    print("  F11                : toggle windowed / maximized (starts maximized)")
    print("  Shift+O            : toggle console log (shows print() output in fullscreen)")
    print("  Shift+I            : toggle hand icons (text mode is default)")
    print("  Hover over buttons : show their action (from editor tool)")
    print("  Ctrl+Q             : quit")
    print("  W (till)           : face the customer")
    print("  S (till)           : leave till to bar (till re-opens at tillDrinks)")
    print("  S (customer)       : back to the till screen you came from")
    print("  ESC                : return from till sub-menu to tillDrinks")
    print("============================================================================\n")

    if sys.platform.startswith("linux"):
        os.environ.setdefault("SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS", "0")

    pygame.init()
    pygame.display.set_caption(_window_caption())

    # Start maximized (title bar kept). F11 toggles windowed 1280×720.
    screen, is_fullscreen, display_mode = AIsetGameDisplay(pygame, fullscreen=True)
    print(f"Display: {display_mode}  (F11 toggles windowed)")
    clock = pygame.time.Clock()

    vx, vy, vw, vh, border_radius, frame_image = load_till_viewport(images_dir)
    till_frame_surf = load_till_frame_surface(
        images_dir, pygame, frame_image=frame_image)
    customer_frame_surf = load_customer_frame_surface(images_dir, pygame)
    if customer_frame_surf is not None:
        print("Customer frame: Bar Images/customerFrame.*")
    else:
        print("Customer frame: flat background (add Bar Images/customerFrame.jpg)")
    customer_roster = AIloadCustomerRoster(images_dir)
    cv_x, cv_y, cv_w, cv_h, cv_name_gap, cv_name_height = load_customer_viewport(images_dir)
    customer_headshot_cache: dict[str, object] = {}
    current_customer: CustomerEntry | None = None
    current_customer_surf = None

    def _load_customer_headshot(entry: CustomerEntry):
        cached = customer_headshot_cache.get(entry.image_file)
        if cached is not None:
            return cached
        surf = load_customer_headshot_surface(images_dir, entry.image_file, pygame)
        if surf is not None:
            customer_headshot_cache[entry.image_file] = surf
        return surf

    def _pick_new_customer(*, exclude_name: str | None = None) -> None:
        nonlocal current_customer, current_customer_surf
        current_customer = AIpickRandomCustomer(
            customer_roster, exclude_name=exclude_name)
        current_customer_surf = None
        if current_customer is not None:
            current_customer_surf = _load_customer_headshot(current_customer)
            print(f"Customer: {current_customer.display_name}")

    _pick_new_customer()
    if customer_roster:
        print(f"Customer roster: {len(customer_roster)} in customers.txt / Customer Images/")
        print(
            f"Portrait viewport: x={cv_x:.3f} y={cv_y:.3f} width={cv_w:.3f} "
            f"height={cv_h:.3f}"
        )
        print("  Tune with: python -m src.bar.customer_viewport_tool")
    else:
        print("Customer roster: empty (add Customer Images/ + customers.txt)")
    if till_frame_surf is not None:
        print(f"Till frame: Till Images/{frame_image}")
        print(
            f"Till viewport: x={vx:.3f} y={vy:.3f} width={vw:.3f} "
            f"height={vh:.3f} border_radius={border_radius:.3f}"
        )
        print("  Tune with: python -m src.bar.till_viewport_tool")
    else:
        print(
            "Till frame: uniform margin around till screens "
            f"(add Till Images/tillFrame.jpg to use a bezel image)"
        )

    # Create fonts early so we can use them for the loading screen
    font = ui_font(28)
    small_font = ui_font(20)
    console_font = ui_font(15)

    # Load pixel art item icons for hand display (from NeuroMods/Bar/Item Images/)
    item_icon_dir = _get_bar_images_root() / "Item Images"
    item_icons = {}
    _icon_max_load = 288  # largest on-screen hand icon; avoid loading 1024² textures
    icon_map = {
        "empty_beer_glass": "empty_beer_glass.png",
        "full_beer_glass": "full_beer_glass.png",
        "empty_wine_glass": "empty_wine_glass.png",
        "white_wine_glass": "white_wine_glass.png",
        "red_wine_glass": "red_wine_glass.png",
        "rose_wine_glass": "rose_wine_glass.png",
        "metal_shaker": "metal_shaker.png",
        "shot_glass": "shot_glass.png",
        "lemon_wheel": "lemon_wheel.png",
        "lime_wheel": "lime_wheel.png",
        "orange_wheel": "orange_wheel.png",
        # Updated to new take: naming scheme (camel&)
        "madriGlass": "madri_glass.png",
        "coorsGlass": "coors_glass.png",
        "carlingGlass": "carling_glass.png",
        "guinessGlass": "guiness_glass.png",
        "caffreysGlass": "caffreys_glass.png",
        "doombarGlass": "doombar_glass.png",
        "lammaGlass": "lamma_glass.png",
        "limelightGlass": "limelight_glass.png",
        "allegraGlass": "allegra_glass.png",
        "capriGlass": "capri_glass.png",
        "martiniGlass": "martini_glass.png",
        "hiBallGlass": "hi_ball_glass.png",
        "champagneGlass": "champagne_glass.png",
        "bostonShaker": "boston_shaker.png",
        # legacy snake keys kept for backward map compat (item_icon_map.json may use old)
        "madri_glass": "madri_glass.png",
        "coors_glass": "coors_glass.png",
        "carling_glass": "carling_glass.png",
        "guiness_glass": "guiness_glass.png",
        "caffreys_glass": "caffreys_glass.png",
        "doombar_glass": "doombar_glass.png",
        "lamma_glass": "lamma_glass.png",
        "limelight_glass": "limelight_glass.png",
        "allegra_glass": "allegra_glass.png",
        "capri_glass": "capri_glass.png",
        "martini_glass": "martini_glass.png",
        "hi_ball_glass": "hi_ball_glass.png",
        "champagne_glass": "champagne_glass.png",
        "boston_shaker": "boston_shaker.png",
    }
    for key, fname in icon_map.items():
        p = item_icon_dir / fname
        if p.exists():
            try:
                img = pygame.image.load(str(p)).convert_alpha()
                iw, ih = img.get_size()
                if max(iw, ih) > _icon_max_load:
                    scale = _icon_max_load / max(iw, ih)
                    nw = max(1, int(iw * scale))
                    nh = max(1, int(ih * scale))
                    img = pygame.transform.smoothscale(img, (nw, nh))
                item_icons[key] = img
            except Exception as e:
                print(f"Warning: could not load {p}: {e}")
        else:
            print(f"Warning: item icon missing: {p}")

    # Load user-defined mapping from the icon mapper tool (preferred over hardcoded logic)
    item_icon_map = {}
    map_path = _get_bar_images_root() / "item_icon_map.json"
    if map_path.exists():
        try:
            with open(map_path, "r") as f:
                item_icon_map = json.load(f)
        except Exception as e:
            print(f"Warning: could not load item_icon_map.json: {e}")

    def get_icon_for_item(item):
        if not item:
            return None
        item_lower = str(item).lower().strip()
        # Prefer mappings from the icon mapper tool (item_icon_map.json)
        for key, icon_name in item_icon_map.items():
            if key.lower() == item_lower or key.lower() in item_lower:
                if icon_name in item_icons:
                    return item_icons[icon_name]
        # Fall back to the (now mostly legacy) hardcoded logic below
        item = item_lower
        # Specific beer glasses (new 32x32) -- support new take: camel& naming + legacy snake
        if "madri_glass" in item or "madriglass" in item:
            return item_icons.get("madri_glass") or item_icons.get("madriGlass")
        if "coors_glass" in item or "coorsglass" in item:
            return item_icons.get("coors_glass") or item_icons.get("coorsGlass")
        if "carling_glass" in item or "carlingglass" in item:
            return item_icons.get("carling_glass") or item_icons.get("carlingGlass")
        if "guiness_glass" in item or "guinessglass" in item:
            return item_icons.get("guiness_glass") or item_icons.get("guinessGlass")
        if "caffreys_glass" in item or "caffreysglass" in item:
            if "poured" in item:
                return item_icons.get("full_beer_glass")
            return item_icons.get("caffreys_glass") or item_icons.get("caffreysGlass")
        if "doombar_glass" in item or "doombarglass" in item:
            return item_icons.get("doombar_glass") or item_icons.get("doombarGlass")
        if "lamma_glass" in item or "lammaglass" in item:
            return item_icons.get("lamma_glass") or item_icons.get("lammaGlass")
        if "limelight_glass" in item or "limitness_glass" in item or "limelightglass" in item:
            return item_icons.get("limelight_glass") or item_icons.get("limelightGlass")
        if "allegra_glass" in item or "allegraglass" in item:
            return item_icons.get("allegra_glass") or item_icons.get("allegraGlass")
        if "capri_glass" in item or "capriglass" in item:
            return item_icons.get("capri_glass") or item_icons.get("capriGlass")
        if "tall_glass" in item or "hi_ball" in item or "broadway" in item or "tallglass" in item or "hiballglass" in item:
            return item_icons.get("hi_ball_glass") or item_icons.get("hiBallGlass")
        if "short_glass" in item or "shortglass" in item:
            return item_icons.get("shot_glass")
        # Poured beer glasses first (fallback)
        if "poured" in item and ("glass" in item or "beer" in item):
            return item_icons.get("full_beer_glass")
        # Generic beer glasses (new names + legacy)
        beer_glass_names = ["guiness_glass", "lamma_glass", "doombar_glass", "caffreys_glass", "coors_glass", "carling_glass", "madri_glass",
                            "guinessGlass", "lammaGlass", "doombarGlass", "caffreysGlass", "coorsGlass", "carlingGlass", "madriGlass"]
        for bg in beer_glass_names:
            if bg in item:
                return item_icons.get("empty_beer_glass")
        # Wines by prefix or name
        if item.startswith("white_") or ("white" in item and "wine" in item):
            return item_icons.get("white_wine_glass")
        if item.startswith("red_") or ("red" in item and "wine" in item):
            return item_icons.get("red_wine_glass")
        if item.startswith("rose_") or ("rose" in item and "wine" in item):
            return item_icons.get("rose_wine_glass")
        # Cocktails from bar.nm (new camel& names too)
        if "martini_glass" in item or "passion_fruit_martini" in item or "tails_passion" in item or "martiniglass" in item:
            return item_icons.get("martini_glass") or item_icons.get("martiniGlass")
        if "vina_juliette" in item or "champagne_glass" in item or "aperol_spritz" in item or "schweppes_aperitivo" in item or "champagneglass" in item:
            return item_icons.get("champagne_glass") or item_icons.get("champagneGlass")
        if "capri_glass" in item or "pina_colada" in item or "tails_pina" in item or "rum_punch" in item or "tails_rum" in item or "capriglass" in item:
            return item_icons.get("capri_glass") or item_icons.get("capriGlass")
        if "hi_ball" in item or "broadway" in item or "blue_lagoon" in item or "mojito" in item or "tropical_woo" in item or "schweppes_mojito" in item or "hiballglass" in item:
            return item_icons.get("hi_ball_glass") or item_icons.get("hiBallGlass")
        # Shaker (new names)
        if "shaker" in item or "boston" in item or "bostonshaker" in item:
            return item_icons.get("boston_shaker") or item_icons.get("bostonShaker")
        # Slices (new camel)
        if "lemon" in item or "lemon_slice" in item or "lemonslice" in item:
            return item_icons.get("lemon_wheel")
        if "lime" in item or "lime_slice" in item or "limeslice" in item:
            return item_icons.get("lime_wheel")
        if "orange" in item or "orange_slice" in item or "orangeslice" in item:
            return item_icons.get("orange_wheel")
        # Shot / thimbles / small glasses (new)
        if "shot" in item or "thimble" in item or "shots_glass" in item or "shotsglass" in item or "mlthimble" in item:
            return item_icons.get("shot_glass")
        # other wine glasses or empty
        if "wine_glass" in item:
            if "white" in item:
                return item_icons.get("white_wine_glass")
            if "red" in item:
                return item_icons.get("red_wine_glass")
            if "rose" in item:
                return item_icons.get("rose_wine_glass")
            return item_icons.get("empty_wine_glass")
        return None

    # Very minimal in-game console: redirects stdout so print() output is visible
    # while in fullscreen (where the terminal is hidden).
    class _GameConsole:
        def __init__(self, max_lines=7):
            self.lines = []
            self.max_lines = max_lines
            self._real = sys.stdout

        def write(self, text):
            if text:
                for line in text.rstrip("\n").split("\n"):
                    line = line.strip()
                    if line:
                        self.lines.append(line)
                        if len(self.lines) > self.max_lines:
                            self.lines.pop(0)
            self._real.write(text)

        def flush(self):
            self._real.flush()

    _console = _GameConsole()
    sys.stdout = _console

    # Pre-load all the bar images (many high-res photos). Show a basic loading screen
    # so the user doesn't just see a frozen window.
    surface_cache: Dict[str, pygame.Surface] = {}
    original_sizes: Dict[str, tuple[int, int]] = {}

    loadable_keys = [k for k in VIEW_ORDER if k != "customer"]
    total = len(loadable_keys)
    loaded_count = 0
    last_loaded_surf = None

    for key in VIEW_ORDER:
        if key == "customer":
            surface_cache[key] = None  # special blank screen
            original_sizes[key] = (0, 0)
            continue

        # --- Basic loading screen ---
        screen.fill(ui_theme.LOAD_BG)
        win_w, win_h = screen.get_size()

        title_col = (
            ui_theme.LOAD_TITLE_PRACTICE
            if _practice_mode or not _review_mode
            else ui_theme.LOAD_TITLE_REVIEW
        )
        title_surf = font.render(
            f"Loading Bar Trainer ({_session_mode_label()})", True, title_col
        )
        screen.blit(title_surf, (win_w // 2 - title_surf.get_width() // 2, 48))

        if last_loaded_surf is not None:
            details_y = _blit_loading_preview(screen, last_loaded_surf, win_w, win_h)
        else:
            details_y = win_h // 2 - 50

        # What we're currently loading
        loading_surf = small_font.render(f"Loading {key} ...", True, ui_theme.PANEL_BODY)
        screen.blit(loading_surf, (win_w // 2 - loading_surf.get_width() // 2, details_y))

        # Progress text
        prog_y = details_y + 28
        prog_text = small_font.render(
            f"Images loaded: {loaded_count} / {total}", True, ui_theme.PANEL_MUTED)
        screen.blit(prog_text, (win_w // 2 - prog_text.get_width() // 2, prog_y))

        # Simple progress bar
        bar_w = min(480, win_w - 80)
        bar_h = 16
        bar_x = (win_w - bar_w) // 2
        bar_y = prog_y + 28
        pygame.draw.rect(
            screen, ui_theme.LOAD_BAR_BG, (bar_x, bar_y, bar_w, bar_h), border_radius=4)
        fill_w = int(bar_w * (loaded_count / max(1, total)))
        if fill_w > 0:
            pygame.draw.rect(
                screen, ui_theme.LOAD_BAR_FILL, (bar_x, bar_y, fill_w, bar_h), border_radius=4)
        pygame.draw.rect(
            screen, ui_theme.LOAD_BAR_BORDER, (bar_x, bar_y, bar_w, bar_h), 1, border_radius=4)

        # Helpful note
        note = small_font.render(
            "High-resolution photos — first run can take several seconds",
            True, ui_theme.LOAD_MUTED,
        )
        screen.blit(note, (win_w // 2 - note.get_width() // 2, bar_y + 36))

        pygame.display.flip()

        # Keep the window responsive during long loads and allow quitting
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                import sys as _sys
                _sys.exit(0)
        pygame.event.pump()

        # Actually load the image
        view = get_view(key)
        surf = load_image_surface(view, images_dir)
        surface_cache[key] = surf
        original_sizes[key] = surf.get_size()
        last_loaded_surf = surf
        print(f"  Loaded {key}: {original_sizes[key][0]}x{original_sizes[key][1]}")
        loaded_count += 1

    current_key = "1W1"  # Start at spot 1 facing West (standing) — facing the till
    till_return_key = TILL_HOME  # till screen to restore when leaving customer (S)

    show_console = False  # console box hidden by default; toggle with Shift+O
    show_hand_icons = False  # text fallback by default; toggle with Shift+I for (pixel art) hand icons

    running = True
    hover_grow = ui_theme.AIHoverGrow()
    while running:
        dt_seconds = clock.tick(60) / 1000.0
        # Dynamic size each frame (supports resizing and F11 fullscreen toggle)
        win_w, win_h = screen.get_size()
        mx, my = pygame.mouse.get_pos()
        tooltip_text = None

        if pending_send_items is not None:
            _, _, _, _, send_popup_option_rects = _send_grade_popup_layout(
                win_w, win_h, len(pending_send_items))
            for ii, (rect, _grade) in enumerate(send_popup_option_rects):
                rx, ry, rw, rh = rect
                if rx <= mx < rx + rw and ry <= my < ry + rh:
                    send_popup_selection = ii
                    break
        else:
            send_popup_option_rects = []

        # Customer screen: U-shaped overlay (empty top centre, sides + bottom panel).
        cust_layout = AIcomputeCustomerLayout(win_w, win_h)
        PLACED_ITEMS_BOX = cust_layout.placed_box
        SENT_ITEMS_BOX = cust_layout.sent_box
        DEMANDS_BOX = cust_layout.demands_box
        GRADE_AGAIN_RECT = cust_layout.grade_again
        GRADE_HARD_RECT = cust_layout.grade_hard
        GRADE_GOOD_RECT = cust_layout.grade_good
        GRADE_EASY_RECT = cust_layout.grade_easy
        RESET_BUTTON_RECT = cust_layout.reset_placed
        RESET_TILL_BUTTON_RECT = cust_layout.reset_till
        FINISH_BUTTON_RECT = cust_layout.finish_button

        # (Top BAR/FOOD tabs are now expected to be user-added via the editor tool
        # using actions like "switch:tillDrinks", "switch:tillFood", etc.)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.VIDEORESIZE:
                screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
                continue

            elif pending_send_items is not None:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_UP:
                        send_popup_selection = (send_popup_selection - 1) % len(GRADE_OPTIONS)
                        continue
                    if event.key == pygame.K_DOWN:
                        send_popup_selection = (send_popup_selection + 1) % len(GRADE_OPTIONS)
                        continue
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        grade = GRADE_OPTIONS[send_popup_selection][0]
                        for item in pending_send_items:
                            sent_orders.append(item)
                            sent_grades[item] = grade
                        print("=== SENDING ORDER ===")
                        for item in pending_send_items:
                            print(f"  - {item} ({grade_label(grade)})")
                        print("Order sent to kitchen!")
                        orders.clear()
                        pending_send_items = None
                        continue
                    if event.key == pygame.K_ESCAPE:
                        print("Send cancelled — order kept on till.")
                        pending_send_items = None
                        continue
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = event.pos
                    for rect, grade in send_popup_option_rects:
                        rx, ry, rw, rh = rect
                        if rx <= mx < rx + rw and ry <= my < ry + rh:
                            for item in pending_send_items:
                                sent_orders.append(item)
                                sent_grades[item] = grade
                            print("=== SENDING ORDER ===")
                            for item in pending_send_items:
                                print(f"  - {item} ({grade_label(grade)})")
                            print("Order sent to kitchen!")
                            orders.clear()
                            pending_send_items = None
                            break
                    if pending_send_items is not None:
                        continue

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F11:
                    is_fullscreen = not is_fullscreen
                    screen, is_fullscreen, display_mode = AIsetGameDisplay(
                        pygame, fullscreen=is_fullscreen)
                    print(f"Display: {display_mode}")
                    continue

                if event.key == pygame.K_o and (event.mod & pygame.KMOD_SHIFT):
                    show_console = not show_console
                    print(f"Console log: {'ON' if show_console else 'OFF'}")
                    continue

                if event.key == pygame.K_i and (event.mod & pygame.KMOD_SHIFT):
                    show_hand_icons = not show_hand_icons
                    print(f"Hand icons: {'ON' if show_hand_icons else 'OFF'} (text is default)")
                    continue

                if event.key == pygame.K_q and (event.mod & pygame.KMOD_CTRL):
                    running = False
                    continue

                TILL_HOMES = (TILL_HOME, "tillFood")
                if event.key == pygame.K_ESCAPE:
                    if current_key.startswith("till") and current_key not in TILL_HOMES:
                        # ESC in till submenus returns to tillDrinks (no longer used for quitting)
                        current_key = TILL_HOME
                        print(f"Returned to the main till ({TILL_HOME})")
                    # ESC does nothing else (quit is now Ctrl+Q only)
                    continue

                # W from any till screen → customer; remember which till to return to.
                if current_key.startswith("till") and event.key in (pygame.K_w, pygame.K_UP):
                    till_return_key = current_key
                    current_key = "customer"
                    print(f"Facing the customer (return: {till_return_key})")
                    continue

                # S from any till screen → leave to bar; next till visit defaults to tillDrinks.
                if current_key.startswith("till") and event.key in (pygame.K_s, pygame.K_DOWN):
                    current_key = TILL_BAR_EXIT
                    till_return_key = TILL_HOME
                    print(f"Left the till (back to bar; re-opens at {TILL_HOME})")
                    continue

                if current_key == "customer":
                    if event.key in (pygame.K_s, pygame.K_DOWN, pygame.K_b):
                        current_key = till_return_key
                        customer_awaiting_continue = False
                        finish_report_lines = []
                        print(f"Back to {till_return_key}")
                        continue
                    # No left, right, turning, or crouch/stand capability from customer screen
                    continue

                if current_key.startswith("till") and current_key not in TILL_HOMES:
                    # In till sub-menu: ignore bar movement/turn/crouch keys
                    # (W→customer handled above; ESC returns to tillDrinks)
                    continue

                # General forward/back using W/S (or arrows up/down) for position views.
                # Especially useful for E/W facings (facing along the bar): W=forward, S=back.
                # For N/S facings, forward/back may be None (use A/D for along-bar movement).
                if event.key in (pygame.K_w, pygame.K_UP):
                    view = get_view(current_key)
                    nxt = view.go("forward")
                    if nxt:
                        current_key = nxt
                    else:
                        print("  [No view forward from here]")
                    continue

                if event.key in (pygame.K_s, pygame.K_DOWN):
                    view = get_view(current_key)
                    nxt = view.go("back")
                    if nxt:
                        current_key = nxt
                    else:
                        print("  [No view back from here]")
                    continue

                elif event.key == pygame.K_LEFT:
                    # Arrow keys are always map-absolute:
                    # left arrow = west, right arrow = east (on the bar)
                    view = get_view(current_key)
                    nxt = view.go("left")
                    if nxt:
                        current_key = nxt
                    else:
                        print("  [No view to the left (west) from here]")

                elif event.key == pygame.K_RIGHT:
                    view = get_view(current_key)
                    nxt = view.go("right")
                    if nxt:
                        current_key = nxt
                    else:
                        print("  [No view to the right (east) from here]")

                elif event.key == pygame.K_a:
                    # A always moves to player's left (graph "left" neighbor set per facing)
                    view = get_view(current_key)
                    nxt = view.go("left")
                    if nxt:
                        current_key = nxt
                    else:
                        print("  [No view to the left from here]")

                elif event.key == pygame.K_d:
                    # D always moves to player's right (graph "right" neighbor set per facing)
                    view = get_view(current_key)
                    nxt = view.go("right")
                    if nxt:
                        current_key = nxt
                    else:
                        print("  [No view to the right from here]")

                elif event.key in (pygame.K_q,):
                    view = get_view(current_key)
                    nxt = view.go("turn_left") or _turn_key(current_key, clockwise=False)
                    if nxt:
                        current_key = nxt
                    else:
                        print("  [Cannot turn left from here]")

                elif event.key in (pygame.K_e,):
                    view = get_view(current_key)
                    nxt = view.go("turn_right") or _turn_key(current_key, clockwise=True)
                    if nxt:
                        current_key = nxt
                    else:
                        print("  [Cannot turn right from here]")

                elif event.key in (pygame.K_LCTRL, pygame.K_RCTRL, pygame.K_c):
                    # Single-button toggle for height. Primary binding is the Control key
                    # (as per the original design spec). C is kept as a convenient alias
                    # so the toggle works under one logical "crouch/stand" action.
                    # It automatically picks the relevant direction (crouch vs stand).
                    nxt = try_height_toggle(current_key)
                    if nxt:
                        current_key = nxt
                    else:
                        print("  [No height change possible from here]")

                elif event.key == pygame.K_F1:
                    # Future: help overlay
                    print("F1 pressed — (future: show controls + current view hotspots)")

            elif event.type == pygame.MOUSEBUTTONDOWN:
                # Support left click (1) for most actions, and right click (3) specifically for
                # take: and pour: and thimble: buttons (to choose which hand to affect).
                # For pour: click with hand holding BASE/BASEHalf.
                # For thimble: click with hand holding a wine or spirit item.
                # craft: / crafting: only use left click.
                # Other buttons (order, send, switch, grades, etc.) only respond to left click.
                button = event.button
                if button not in (1, 3):
                    continue
                mx, my = event.pos

                if current_key == "customer":
                    # Handle grade buttons, reset, finish only on left click.
                    if button != 1:
                        continue
                    # PLACE grade buttons — both hands placed with the chosen grade.
                    grade_clicks = [
                        (GRADE_AGAIN_RECT, 1, "Again"),
                        (GRADE_HARD_RECT,  2, "Hard"),
                        (GRADE_GOOD_RECT,  3, "Good"),
                        (GRADE_EASY_RECT,  4, "Easy"),
                    ]
                    grade_handled = False
                    for rect, g, label in grade_clicks:
                        if (rect[0] <= mx < rect[0] + rect[2] and
                            rect[1] <= my < rect[1] + rect[3]):
                            placed_any = False
                            for hand_name, item in (("right", right_hand), ("left", left_hand)):
                                if item:
                                    placed.append(item)
                                    placed_grades[item] = g
                                    print(f"Placed {item} on the counter ({label}, grade={g}).")
                                    placed_any = True
                                    if hand_name == "right":
                                        right_hand = None
                                    else:
                                        left_hand = None
                            if not placed_any:
                                print(f"PLACE ({label}): both hands empty.")
                            grade_handled = True
                            break
                    if grade_handled:
                        continue

                    if (RESET_BUTTON_RECT[0] <= mx < RESET_BUTTON_RECT[0] + RESET_BUTTON_RECT[2] and
                        RESET_BUTTON_RECT[1] <= my < RESET_BUTTON_RECT[1] + RESET_BUTTON_RECT[3]):
                        placed.clear()
                        placed_grades.clear()
                        print("Placed items reset.")
                        continue
                    if (RESET_TILL_BUTTON_RECT[0] <= mx < RESET_TILL_BUTTON_RECT[0] + RESET_TILL_BUTTON_RECT[2] and
                        RESET_TILL_BUTTON_RECT[1] <= my < RESET_TILL_BUTTON_RECT[1] + RESET_TILL_BUTTON_RECT[3]):
                        sent_orders.clear()
                        sent_grades.clear()
                        orders.clear()
                        pending_send_items = None
                        print("Till reset (sent items + pending order cleared).")
                        continue
                    if (FINISH_BUTTON_RECT[0] <= mx < FINISH_BUTTON_RECT[0] + FINISH_BUTTON_RECT[2] and
                        FINISH_BUTTON_RECT[1] <= my < FINISH_BUTTON_RECT[1] + FINISH_BUTTON_RECT[3]):
                        if customer_awaiting_continue:
                            finish_report_lines = []
                            customer_awaiting_continue = False
                            placed.clear()
                            placed_grades.clear()
                            sent_orders.clear()
                            sent_grades.clear()
                            left_hand = None
                            right_hand = None
                            current_demands = _sample_next_demands()
                            prev_name = (
                                current_customer.display_name
                                if current_customer is not None else None)
                            _pick_new_customer(exclude_name=prev_name)
                            print("A new customer has arrived with fresh demands!")
                        else:
                            success, total, succeeded, finish_report_lines = _score_customer_demands(
                                current_demands, placed, sent_orders,
                                BEER_GLASS_TO_DRINK, BURGER_DEMANDS)
                            print("=== CUSTOMER FINISHED ===")
                            for line in finish_report_lines:
                                print(line)

                            if _review_mode and not _practice_mode:
                                for demand in list(current_demands):
                                    if demand not in _due_map:
                                        continue
                                    if demand not in succeeded:
                                        grade = 1
                                    else:
                                        grade = _grade_for_fulfilled_demand(
                                            demand, placed_grades, sent_grades, BEER_GLASS_TO_DRINK)
                                    adapt_id = _due_map.pop(demand)
                                    try:
                                        from ..core.db import getAdaptData, updateDB
                                        from ..core.scheduler import schedulerReview
                                        full, _, _ = getAdaptData(adapt_id)
                                        if full:
                                            sched_dict, new_due = schedulerReview(full, grade=grade)
                                            updateDB(
                                                adapt_id=adapt_id,
                                                scheduling_dict=sched_dict,
                                                newDue=new_due)
                                            print(
                                                f"  [review] {demand} -> {grade_label(grade)} "
                                                f"({grade}) adapt_id={adapt_id}")
                                    except Exception as ex:
                                        print(f"  [review] FSRS update error for {demand}: {ex}")

                                if not _due_map and not _practice_mode:
                                    _practice_mode = True
                                    pygame.display.set_caption(_window_caption())
                                    finish_report_lines.append("")
                                    finish_report_lines.append(
                                        "All cards reviewed. Exit or keep playing.")

                            customer_awaiting_continue = True
                            placed.clear()
                            placed_grades.clear()
                            sent_orders.clear()
                            sent_grades.clear()
                            left_hand = None
                            right_hand = None
                        continue
                    # Other clicks on customer screen: ignore for now
                    continue

                view = get_view(current_key)
                orig_w, orig_h = original_sizes.get(current_key, (3160, 1815))

                # We need the current scaled + blit position.
                # Recompute it here (cheap) so we don't have to store it.
                current_surf = surface_cache[current_key]
                photo_layout = layout_view_photo(
                    current_key, current_surf, win_w, win_h,
                    is_fullscreen=is_fullscreen,
                    frame_surface=till_frame_surf,
                    pygame_module=pygame,
                )
                bx, by = photo_layout.blit_x, photo_layout.blit_y
                sw, sh = photo_layout.width, photo_layout.height

                ix, iy = screen_to_image_coords(mx, my, bx, by, sw, sh, orig_w, orig_h)

                if ix >= 0:
                    # Always check tool-created photo buttons for current view (now supports all images: till + glasses/positions)
                    btns = TILL_PHOTO_BUTTON_DATA.get(current_key, [])
                    button_handled = False
                    for btn in btns:
                        tx, ty, tw, th = btn["rect"]
                        if tx <= ix < tx + tw and ty <= iy < ty + th:
                            action = btn.get("action", "")
                            if action == "void" or action.startswith("void:"):
                                # void: simply removes the most recently added item from the current order list
                                if button == 1:
                                    if orders:
                                        removed = orders.pop()
                                        print(f"Voided last order: {removed}")
                                    else:
                                        print("No orders to void.")
                            elif ":" in action:
                                prefix, value = action.split(":", 1)
                                value = value.strip()
                                if prefix == "order":
                                    if button == 1:
                                        orders.append(value)
                                        print(f"Added to order: {value}")
                                elif prefix in ("switch", "go_to"):
                                    if button == 1:
                                        if value in VIEWS:
                                            current_key = value
                                            print(f"Switched to till screen: {value}")
                                        else:
                                            print(f"Invalid switch target: {value}")
                                elif prefix == "take":
                                    # Left click (1) -> left hand; right click (3) -> right hand.
                                    # Spirit shot pour: shotsGlass/shotGlass + take:spirit → spiritSingle;
                                    # same spirit again → spiritDouble; after Double, no further pour.
                                    if not value:
                                        pass
                                    elif button == 3:
                                        new_item, handled = try_spirit_shot_pour(right_hand, value)
                                        if handled:
                                            if new_item != right_hand:
                                                print(f"Spirit shot pour (right): {right_hand} + {value} → {new_item}")
                                            right_hand = new_item
                                        else:
                                            right_hand = value
                                            print(f"Took {value} into right hand (overwrote previous).")
                                    else:
                                        new_item, handled = try_spirit_shot_pour(left_hand, value)
                                        if handled:
                                            if new_item != left_hand:
                                                print(f"Spirit shot pour (left): {left_hand} + {value} → {new_item}")
                                            left_hand = new_item
                                        else:
                                            left_hand = value
                                            print(f"Took {value} into left hand (overwrote previous).")
                                elif prefix == "pour":
                                    # New multi-stage pour: button action "pour:BASE" (e.g. pour:madriGlass)
                                    # Click *with the specific hand* (button 1 = left, button 3 = right) that holds the item.
                                    # BASE → BASEHalf (first click with matching hand)
                                    # BASEHalf → BASEFull (second click)
                                    # BASEFull or wrong item → nothing
                                    base = value
                                    half = base + "Half"
                                    full = base + "Full"

                                    if button == 1:  # left hand click
                                        if left_hand == base:
                                            left_hand = half
                                            print(f"Poured to half in left hand: {base} → {half}")
                                        elif left_hand == half:
                                            left_hand = full
                                            print(f"Poured to full in left hand: {half} → {full}")
                                        elif left_hand == full:
                                            # do nothing
                                            pass
                                        else:
                                            # do nothing (wrong item)
                                            pass
                                    elif button == 3:  # right hand click
                                        if right_hand == base:
                                            right_hand = half
                                            print(f"Poured to half in right hand: {base} → {half}")
                                        elif right_hand == half:
                                            right_hand = full
                                            print(f"Poured to full in right hand: {half} → {full}")
                                        elif right_hand == full:
                                            # do nothing
                                            pass
                                        else:
                                            # do nothing (wrong item)
                                            pass
                                elif prefix == "crafting":
                                    # New crafting mechanic: left-click a "crafting:RESULT" button
                                    # while holding the exact required pair of items (one in each hand).
                                    # Removes both and places RESULT in the right hand.
                                    if button == 1:
                                        target = value
                                        hands_set = frozenset([h for h in (left_hand, right_hand) if h])
                                        required = CRAFT_RECIPES.get(target)
                                        if required and hands_set == required:
                                            print(f"Crafted {target} from {left_hand} + {right_hand} (placed in right hand).")
                                            left_hand = None
                                            right_hand = target
                                        else:
                                            print(f"Cannot craft '{target}' with hands ({left_hand}, {right_hand}). "
                                                  f"Required: {required or 'unknown recipe'}.")
                                elif prefix == "craft":
                                    # craft: / craft:combine — merge thimble pours in both hands.
                                    # Both must be measured (suffix ml); same base name; result → right hand.
                                    if button == 1:
                                        combined = combine_measured_pours(left_hand, right_hand)
                                        if combined:
                                            print(f"Combined pours: {left_hand} + {right_hand} → {combined} (in right hand)")
                                            left_hand = None
                                            right_hand = combined
                                        else:
                                            print(f"Cannot combine pours with hands ({left_hand}, {right_hand}). "
                                                  "Need the same thimble-measured wine or spirit in each hand "
                                                  "(e.g. redWineX25 + redWineX125; unmeasured bottles do not work).")
                                elif prefix == "opener":
                                    if button == 1:
                                        new_item, ok = try_open_bottle(left_hand)
                                        if ok and new_item:
                                            print(f"Opened bottle (left): {left_hand} → {new_item}")
                                            left_hand = new_item
                                        else:
                                            print(
                                                f"Cannot open with opener (left hand: {left_hand or 'empty'}). "
                                                "Need a sealed bottle (j20, soft, *Zero, etc.).")
                                    elif button == 3:
                                        new_item, ok = try_open_bottle(right_hand)
                                        if ok and new_item:
                                            print(f"Opened bottle (right): {right_hand} → {new_item}")
                                            right_hand = new_item
                                        else:
                                            print(
                                                f"Cannot open with opener (right hand: {right_hand or 'empty'}). "
                                                "Need a sealed bottle (j20, soft, *Zero, etc.).")
                                elif prefix == "thimble":
                                    # Thimble measure: thimble:25 / thimble:50 / thimble:125
                                    # Works on wines and spirits (not softs, cans, beer, crisps, kids drinks, etc.).
                                    size_str = value.strip()
                                    try:
                                        sz = int(size_str)
                                    except ValueError:
                                        print(f"Invalid thimble size: {size_str}")
                                    else:
                                        if button == 1 and can_thimble(left_hand):
                                            old = left_hand
                                            left_hand = _apply_thimble(old, sz)
                                            print(f"Thimbled left hand to {sz}: {old} → {left_hand}")
                                        elif button == 3 and can_thimble(right_hand):
                                            old = right_hand
                                            right_hand = _apply_thimble(old, sz)
                                            print(f"Thimbled right hand to {sz}: {old} → {right_hand}")
                            elif action == "send_order":
                                if button == 1:
                                    if orders:
                                        pending_send_items = list(orders)
                                        send_popup_selection = 2
                                        print("Choose send grade (↑/↓ + Enter, click, or Esc to cancel)")
                                    else:
                                        print("No items in current order.")
                            elif action in SEND_GRADE_MAP:
                                if button == 1:
                                    send_grade = SEND_GRADE_MAP[action]
                                    if orders:
                                        for item in orders:
                                            sent_orders.append(item)
                                            sent_grades[item] = send_grade
                                        print("=== SENDING ORDER ===")
                                        for item in orders:
                                            print(f"  - {item} ({grade_label(send_grade)})")
                                        print("Order sent to kitchen!")
                                        orders.clear()
                                    else:
                                        print("No items in current order.")
                            else:
                                pass
                            button_handled = True

                    if not button_handled and button == 1:
                        if current_key.startswith("till"):
                            # Legacy back rect for submenus (top nav is preferred way now)
                            bx1, by1, bw, bh = TILL_SUB_BACK_RECT
                            if bx1 <= ix < bx1 + bw and by1 <= iy < by1 + bh:
                                if "food" in current_key or "Food" in current_key:
                                    current_key = "tillFood"
                                else:
                                    current_key = "tillDrinks"
                                print("Returned to menu home")
                            else:
                                print(f"Clicked in submenu '{current_key}' at ({ix}, {iy}) "
                                      f"(future: select/ring item)  [use in-photo buttons or the back rect to return]")
                        elif not current_key.startswith("till"):
                            # For non-till views (e.g. position photos), print coords if no button hit (for further editing)
                            print(f"Click on '{current_key}' at original pixels: ({ix}, {iy})  "
                                  f"[screen=({mx},{my})]")
                else:
                    if button == 1:
                        print(f"Click outside photo area on '{current_key}'")

        # ---------------- Rendering ----------------
        screen.fill(ui_theme.BG_LETTERBOX)

        photo_rect = None
        if current_key == "customer":
            AIdrawCustomerBackground(
                screen, customer_frame_surf, win_w, win_h, pygame)
            if current_customer is not None and current_customer_surf is not None:
                AIdrawCustomerPortrait(
                    screen,
                    current_customer_surf,
                    current_customer.display_name,
                    small_font,
                    win_w,
                    win_h,
                    pygame,
                    viewport=(cv_x, cv_y, cv_w, cv_h),
                    name_gap=cv_name_gap,
                    name_height=cv_name_height,
                )

            dem_x, dem_y, dem_w, layout_dem_h = DEMANDS_BOX
            dem_pad_x = 12
            dem_pad_y = 12
            dem_line_h = 18
            text_width = cust_layout.demands_text_width
            panel_alpha = ui_theme.TRANSLUCENT_PANEL_ALPHA
            btn_alpha = ui_theme.TRANSLUCENT_BUTTON_ALPHA

            bottom_margin = max(14, int(min(win_w, win_h) * 0.022))
            dem_top = dem_y
            max_dem_h = win_h - dem_top - bottom_margin
            content_h = _customer_demands_content_height(
                small_font=small_font,
                console_font=console_font,
                text_width=text_width,
                demand_keys=current_demands,
                report_lines=finish_report_lines,
                showing_report=customer_awaiting_continue,
                line_h=dem_line_h,
                pad_y=dem_pad_y,
            )
            dem_h = min(max_dem_h, max(content_h, 96))
            dem_y = win_h - bottom_margin - dem_h
            if dem_y < dem_top:
                dem_y = dem_top
                dem_h = win_h - bottom_margin - dem_y

            demand_hover_regions: list[tuple[tuple[int, int, int, int], str]] = []
            hovered_demand_key: str | None = None

            demands_rect = (dem_x, dem_y, dem_w, dem_h)
            dem_hovered = ui_theme.point_in_rect(mx, my, demands_rect)
            ui_theme.draw_panel(
                screen, demands_rect, hovered=dem_hovered, alpha=panel_alpha)

            y = dem_y + dem_pad_y
            clip_rect = pygame.Rect(dem_x + 1, dem_y + 1, dem_w - 2, dem_h - 2)
            prev_clip = screen.get_clip()
            screen.set_clip(clip_rect)

            def _blit_dem_line(
                line: str,
                color: tuple[int, int, int] = ui_theme.PANEL_BODY,
                *,
                use_console_font: bool = False,
            ) -> None:
                nonlocal y
                if y + dem_line_h > dem_y + dem_h - dem_pad_y:
                    return
                fnt = console_font if use_console_font else small_font
                txt = fnt.render(line, True, color)
                screen.blit(txt, (dem_x + dem_pad_x, y))
                y += dem_line_h

            if customer_awaiting_continue and finish_report_lines:
                for line in finish_report_lines:
                    for wrapped in _wrap_text_lines(console_font, line, text_width):
                        col = ui_theme.YELLOW_BRIGHT
                        if wrapped.startswith("MISSING"):
                            col = (255, 90, 90)
                        elif wrapped.startswith("EXTRA"):
                            col = (255, 165, 70)
                        elif wrapped.startswith("OK"):
                            col = (160, 255, 160)
                        elif "/" in wrapped and "successful" in wrapped:
                            col = ui_theme.YELLOW
                        _blit_dem_line(wrapped, col, use_console_font=True)
            else:
                for line in _wrap_text_lines(small_font, "Customer demands:", text_width):
                    _blit_dem_line(line, ui_theme.PANEL_HEADER)
                _blit_dem_line("")

                for demand_key in current_demands:
                    block_top = y
                    for line in _wrap_bullet_lines(
                            small_font, format_demand(demand_key), text_width):
                        _blit_dem_line(line)
                    if y > block_top:
                        demand_hover_regions.append(
                            ((dem_x, block_top, dem_w, y - block_top), demand_key))

                _blit_dem_line("")
                for paragraph in (
                    "Left-click take buttons (on position views) to put glass in left hand; "
                    "right-click for right hand.",
                    "On customer: grade buttons place both hands on the counter + rate recall.",
                ):
                    for line in _wrap_text_lines(small_font, paragraph, text_width):
                        _blit_dem_line(line, ui_theme.HELP_FOOTER)
                    _blit_dem_line("")

            screen.set_clip(prev_clip)

            for rect, demand_key in demand_hover_regions:
                rx, ry, rw, rh = rect
                if rx <= mx < rx + rw and ry <= my < ry + rh:
                    hovered_demand_key = demand_key
                    break

            placed_hovered = ui_theme.point_in_rect(mx, my, PLACED_ITEMS_BOX)
            ui_theme.draw_panel(
                screen, PLACED_ITEMS_BOX, hovered=placed_hovered, alpha=panel_alpha)
            py = PLACED_ITEMS_BOX[1] + 10
            ptxt = small_font.render("Placed on counter:", True, ui_theme.PANEL_HEADER)
            screen.blit(ptxt, (PLACED_ITEMS_BOX[0] + 8, py))
            py += 20
            if placed:
                for item in placed:
                    g = placed_grades.get(item)
                    label = f"- {format_item_label(item)}"
                    if g is not None:
                        label += f" ({grade_label(g)})"
                    itxt = small_font.render(label, True, ui_theme.PANEL_BODY)
                    screen.blit(itxt, (PLACED_ITEMS_BOX[0] + 8, py))
                    py += 16
            else:
                itxt = small_font.render("(none)", True, ui_theme.PANEL_MUTED)
                screen.blit(itxt, (PLACED_ITEMS_BOX[0] + 8, py))

            # Sent from till — right side, same size as placed box
            sent_hovered = ui_theme.point_in_rect(mx, my, SENT_ITEMS_BOX)
            ui_theme.draw_panel(
                screen, SENT_ITEMS_BOX, hovered=sent_hovered, alpha=panel_alpha)
            py = SENT_ITEMS_BOX[1] + 10
            stxt = small_font.render("Sent from till:", True, ui_theme.PANEL_HEADER)
            screen.blit(stxt, (SENT_ITEMS_BOX[0] + 8, py))
            py += 20
            if sent_orders:
                for item in sent_orders:
                    g = sent_grades.get(item)
                    label = f"- {format_item_label(item)}"
                    if g is not None:
                        label += f" ({grade_label(g)})"
                    itxt = small_font.render(label, True, ui_theme.PANEL_BODY)
                    screen.blit(itxt, (SENT_ITEMS_BOX[0] + 8, py))
                    py += 16
            else:
                itxt = small_font.render("(none)", True, ui_theme.PANEL_MUTED)
                screen.blit(itxt, (SENT_ITEMS_BOX[0] + 8, py))

            # Left side below placed box: PLACE label + grade buttons + reset
            place_label = small_font.render("PLACE", True, ui_theme.PANEL_ACCENT)
            place_label_x = PLACED_ITEMS_BOX[0] + 8
            place_label_y = PLACED_ITEMS_BOX[1] + PLACED_ITEMS_BOX[3] + 12
            screen.blit(place_label, (place_label_x, place_label_y))

            # Hover for customer action buttons (sets tooltip for the action-on-hover feature)
            if (GRADE_AGAIN_RECT[0] <= mx < GRADE_AGAIN_RECT[0] + GRADE_AGAIN_RECT[2] and
                    GRADE_AGAIN_RECT[1] <= my < GRADE_AGAIN_RECT[1] + GRADE_AGAIN_RECT[3]):
                tooltip_text = "Place both hands on counter (self-grade: Again)"
            elif (GRADE_HARD_RECT[0] <= mx < GRADE_HARD_RECT[0] + GRADE_HARD_RECT[2] and
                    GRADE_HARD_RECT[1] <= my < GRADE_HARD_RECT[1] + GRADE_HARD_RECT[3]):
                tooltip_text = "Place both hands on counter (self-grade: Hard)"
            elif (GRADE_GOOD_RECT[0] <= mx < GRADE_GOOD_RECT[0] + GRADE_GOOD_RECT[2] and
                    GRADE_GOOD_RECT[1] <= my < GRADE_GOOD_RECT[1] + GRADE_GOOD_RECT[3]):
                tooltip_text = "Place both hands on counter (self-grade: Good)"
            elif (GRADE_EASY_RECT[0] <= mx < GRADE_EASY_RECT[0] + GRADE_EASY_RECT[2] and
                    GRADE_EASY_RECT[1] <= my < GRADE_EASY_RECT[1] + GRADE_EASY_RECT[3]):
                tooltip_text = "Place both hands on counter (self-grade: Easy)"
            elif (RESET_BUTTON_RECT[0] <= mx < RESET_BUTTON_RECT[0] + RESET_BUTTON_RECT[2] and
                    RESET_BUTTON_RECT[1] <= my < RESET_BUTTON_RECT[1] + RESET_BUTTON_RECT[3]):
                tooltip_text = "Reset placed items"
            elif (RESET_TILL_BUTTON_RECT[0] <= mx < RESET_TILL_BUTTON_RECT[0] + RESET_TILL_BUTTON_RECT[2] and
                    RESET_TILL_BUTTON_RECT[1] <= my < RESET_TILL_BUTTON_RECT[1] + RESET_TILL_BUTTON_RECT[3]):
                tooltip_text = "Reset sent items and clear pending till order"
            elif (FINISH_BUTTON_RECT[0] <= mx < FINISH_BUTTON_RECT[0] + FINISH_BUTTON_RECT[2] and
                    FINISH_BUTTON_RECT[1] <= my < FINISH_BUTTON_RECT[1] + FINISH_BUTTON_RECT[3]):
                if customer_awaiting_continue:
                    tooltip_text = "Continue: next customer"
                else:
                    tooltip_text = "Finish: score this customer"

            # 4 grade buttons. These place both hands and record the user's self-grade
            # (used for placed demands in review mode on FINISH).
            grade_buttons = [
                (GRADE_AGAIN_RECT, 1),
                (GRADE_HARD_RECT, 2),
                (GRADE_GOOD_RECT, 3),
                (GRADE_EASY_RECT, 4),
            ]
            for rect, grade in grade_buttons:
                g_hover = ui_theme.point_in_rect(mx, my, rect)
                g_blend = hover_grow.update(f"grade:{grade}", g_hover, dt_seconds)
                g_rect = ui_theme.AIscaleRectAroundCenter(
                    rect, hover_grow.scale(g_blend))
                _draw_grade_button(
                    screen, g_rect, grade, GRADE_LABELS[grade], small_font,
                    hover_blend=g_blend)

            # Reset placed (left column, below grade buttons)
            reset_hover = ui_theme.point_in_rect(mx, my, RESET_BUTTON_RECT)
            reset_blend = hover_grow.update("reset_placed", reset_hover, dt_seconds)
            ui_theme.draw_action_button(
                screen,
                ui_theme.AIscaleRectAroundCenter(
                    RESET_BUTTON_RECT, hover_grow.scale(reset_blend)),
                "RESET PLACED", small_font,
                hover_blend=reset_blend,
                alpha=btn_alpha,
            )

            till_reset_hover = ui_theme.point_in_rect(mx, my, RESET_TILL_BUTTON_RECT)
            till_reset_blend = hover_grow.update("reset_till", till_reset_hover, dt_seconds)
            ui_theme.draw_action_button(
                screen,
                ui_theme.AIscaleRectAroundCenter(
                    RESET_TILL_BUTTON_RECT, hover_grow.scale(till_reset_blend)),
                "RESET TILL", small_font,
                hover_blend=till_reset_blend,
                alpha=btn_alpha,
            )
            finish_label = "CONTINUE" if customer_awaiting_continue else "FINISH"
            finish_hover = ui_theme.point_in_rect(mx, my, FINISH_BUTTON_RECT)
            finish_blend = hover_grow.update("finish", finish_hover, dt_seconds)
            ui_theme.draw_action_button(
                screen,
                ui_theme.AIscaleRectAroundCenter(
                    FINISH_BUTTON_RECT, hover_grow.scale(finish_blend)),
                finish_label, small_font,
                hover_blend=finish_blend,
                accent=True,
                alpha=btn_alpha,
            )

            if hovered_demand_key:
                tooltip_text = hovered_demand_key
        else:
            current_view = get_view(current_key)
            current_surf = surface_cache[current_key]

            photo_layout = layout_view_photo(
                current_key, current_surf, win_w, win_h,
                is_fullscreen=is_fullscreen,
                frame_surface=till_frame_surf,
                pygame_module=pygame,
            )
            if photo_layout.frame_scaled is not None:
                screen.blit(
                    photo_layout.frame_scaled,
                    (photo_layout.frame_blit_x, photo_layout.frame_blit_y),
                )
            blit_rounded_surface(
                screen,
                photo_layout.scaled,
                photo_layout.blit_x,
                photo_layout.blit_y,
                photo_layout.clip_radius,
                pygame_module=pygame,
            )
            scaled = photo_layout.scaled
            bx, by = photo_layout.blit_x, photo_layout.blit_y
            photo_rect = (bx, by, photo_layout.width, photo_layout.height)

        # (Left category tabs removed - now managed via the till_button_tool + JSON for all photo buttons)
        # (The previous hardcoded blue/orange BAR/FOOD top buttons have been removed;
        #  users should add equivalent switch buttons themselves via the editor tool,
        #  e.g. action="switch:tillDrinks" for the main bar screen, "switch:tillFood" etc.)

        # Draw photo-space buttons from the editor tool (TILL_PHOTO_BUTTON_DATA)
        # Works for any view (till screens + position/glass images)
        if current_key in original_sizes and current_key != "customer":
            orig_w, orig_h = original_sizes[current_key]
            img_w, img_h = scaled.get_size()
            x_scale = img_w / orig_w
            y_scale = img_h / orig_h

            btns = TILL_PHOTO_BUTTON_DATA.get(current_key, [])
            bar_photo_view = not current_key.startswith("till")
            for btn_index, btn in enumerate(btns):
                tx, ty, tw, th = btn["rect"]
                sx = bx + int(tx * x_scale)
                sy = by + int(ty * y_scale)
                sw = int(tw * x_scale)
                sh = int(th * y_scale)

                is_hovered = sx <= mx <= sx + sw and sy <= my <= sy + sh
                if is_hovered:
                    action = btn.get("action", "")
                    if action:
                        tooltip_text = f"Action: {action}"

                photo_blend = 0.0
                if bar_photo_view:
                    photo_blend = hover_grow.update(
                        f"photo:{current_key}:{btn_index}", is_hovered, dt_seconds)

                _draw_photo_button(
                    screen, sx, sy, sw, sh, btn, small_font,
                    hover_blend=photo_blend,
                    bar_view=bar_photo_view,
                )

        # Hand item icons displayed at bottom corners (over the background image).
        # Left hand icon at bottom-left, right hand at bottom-right.
        # Glass icons have transparent glass so the photo behind shows through.
        # Only in non-till views.
        if not current_key.startswith("till"):
            margin = 8

            r_item = right_hand
            l_item = left_hand
            r_icon = get_icon_for_item(r_item)
            l_icon = get_icon_for_item(l_item)

            # Compute y position based on what will actually be drawn this frame
            if show_hand_icons and (r_icon or l_icon):
                r_str = str(r_item or "").lower()
                l_str = str(l_item or "").lower()
                r_is_measured = is_measured_pour(r_item)
                l_is_measured = is_measured_pour(l_item)
                r_size = 28 if (any(x in r_str for x in ["shot", "thimble", "shots_glass"]) or r_is_measured) else (288 if any(x in r_str for x in ["beer_glass", "wine_glass", "glass", "white_", "red_", "rose_"]) and not any(x in r_str for x in ["shot", "thimble", "shots_glass"]) else 48)
                l_size = 28 if (any(x in l_str for x in ["shot", "thimble", "shots_glass"]) or l_is_measured) else (288 if any(x in l_str for x in ["beer_glass", "wine_glass", "glass", "white_", "red_", "rose_"]) and not any(x in l_str for x in ["shot", "thimble", "shots_glass"]) else 48)
                max_size = max(r_size, l_size, 48)
                y = win_h - max_size - 25
            else:
                y = win_h - 55

            # Right hand (bottom right corner)
            if show_hand_icons and r_icon:
                r_str2 = str(r_item or "").lower()
                is_shot = any(x in r_str2 for x in ["shot", "thimble", "shots_glass"]) or is_measured_pour(r_item)
                is_glass = any(x in r_str2 for x in ["beer_glass", "wine_glass", "glass", "white_", "red_", "rose_"]) and not is_shot
                size = 28 if is_shot else (288 if is_glass else 48)
                scaled = pygame.transform.smoothscale(r_icon, (size, size))
                rx = win_w - size - margin
                screen.blit(scaled, (rx, y))
                if r_item:
                    lbl = console_font.render(
                        str(r_item).replace("_", " ").replace("glass", "").strip()[:14],
                        True, ui_theme.YELLOW_MUTED,
                    )
                    screen.blit(lbl, (rx, y + size + 1))
            else:
                # fallback text mode (icons off via Shift+I or no icon for this item)
                text = f"Right hand: {r_item if r_item else 'empty'}"
                surf = small_font.render(text, True, ui_theme.PANEL_HEADER)
                bw = surf.get_width() + 10
                bh = surf.get_height() + 6
                bx = win_w - bw - margin
                ui_theme.draw_panel(
                    screen, (bx, y, bw, bh),
                    fill=ui_theme.HAND_BADGE_FILL,
                    border=ui_theme.HAND_BADGE_BORDER,
                    radius=4,
                )
                screen.blit(surf, (bx + 5, y + 3))

            # Left hand (bottom left corner)
            if show_hand_icons and l_icon:
                l_str2 = str(l_item or "").lower()
                is_shot = any(x in l_str2 for x in ["shot", "thimble", "shots_glass"]) or is_measured_pour(l_item)
                is_glass = any(x in l_str2 for x in ["beer_glass", "wine_glass", "glass", "white_", "red_", "rose_"]) and not is_shot
                size = 28 if is_shot else (288 if is_glass else 48)
                scaled = pygame.transform.smoothscale(l_icon, (size, size))
                lx = margin
                screen.blit(scaled, (lx, y))
                if l_item:
                    lbl = console_font.render(
                        str(l_item).replace("_", " ").replace("glass", "").strip()[:14],
                        True, ui_theme.YELLOW_MUTED,
                    )
                    screen.blit(lbl, (lx, y + size + 1))
            else:
                # fallback text mode (icons off via Shift+I or no icon for this item)
                text = f"Left hand: {l_item if l_item else 'empty'}"
                surf = small_font.render(text, True, ui_theme.PANEL_HEADER)
                bw = surf.get_width() + 10
                bh = surf.get_height() + 6
                bx = margin
                ui_theme.draw_panel(
                    screen, (bx, y, bw, bh),
                    fill=ui_theme.HAND_BADGE_FILL,
                    border=ui_theme.HAND_BADGE_BORDER,
                    radius=4,
                )
                screen.blit(surf, (bx + 5, y + 3))

        # Overlay info (hidden on till views per user request)
        # current_view is always defined for other uses (e.g. in image drawing)
        current_view = get_view(current_key)
        if not current_key.startswith("till"):
            label = font.render(
                f"{current_view.name}   (key: {current_key})", True, ui_theme.VIEW_LABEL)
            screen.blit(label, (20, 20))

        # --- Minimal minimap (only on position views, not till or customer) ---
        # Horizontal line of 7 grey squares (spot 1 west left → 7 east right).
        # Current spot highlights one side based on facing (N=top, S=bottom, E=right, W=left).
        # North at top. Very basic / FNAF-security-camera-map style.
        if len(current_key) == 3 and current_key[0].isdigit() and current_key[1] in 'NSEW':
            spot = int(current_key[0])
            facing = current_key[1]
            msize = 16
            mgap = 5
            mstart_x = win_w - (7 * msize + 6 * mgap) - 15
            minimap_y = 18
            for i in range(1, 8):
                sx = mstart_x + (i-1) * (msize + mgap)
                sy = minimap_y
                r = (sx, sy, msize, msize)
                if i == spot:
                    pygame.draw.rect(screen, ui_theme.HAND_BADGE_FILL, r)
                    pygame.draw.rect(screen, ui_theme.PANEL_BORDER, r, 1)
                    hl = ui_theme.PANEL_ACCENT
                    t = 2
                    if facing == 'N':
                        pygame.draw.line(screen, hl, (sx+1, sy+1), (sx + msize-2, sy+1), t)
                    elif facing == 'S':
                        pygame.draw.line(screen, hl, (sx+1, sy + msize-2), (sx + msize-2, sy + msize-2), t)
                    elif facing == 'E':
                        pygame.draw.line(screen, hl, (sx + msize-2, sy+1), (sx + msize-2, sy + msize-2), t)
                    elif facing == 'W':
                        pygame.draw.line(screen, hl, (sx+1, sy+1), (sx+1, sy + msize-2), t)
                else:
                    pygame.draw.rect(screen, ui_theme.PANEL_MUTED, r, 1)

            # Crouch/stand indicator: single pixelated icon right below the minimap.
            # Shows only the current stance. Bigger, with a little more vertical gap below the minimap
            # and a larger margin from the right screen edge.
            is_stand = (current_key[2] == '1') if len(current_key) == 3 else False
            px = 4  # bigger pixel size for larger icon (pixelated look)
            ind_y = minimap_y + msize + 10

            # Larger right margin from the screen edge, below the right side of the minimap
            icon_x = win_w - 40

            if is_stand:
                # Standing icon (tall pixelated figure)
                # head
                pygame.draw.rect(screen, ui_theme.YELLOW_BRIGHT, (icon_x + 2*px, ind_y + 0*px, 3*px, 2*px))
                # torso
                pygame.draw.rect(screen, ui_theme.YELLOW, (icon_x + 2*px, ind_y + 2*px, 3*px, 3*px))
                # arms
                pygame.draw.rect(screen, ui_theme.YELLOW_MUTED, (icon_x + 1*px, ind_y + 3*px, 1*px, 2*px))
                pygame.draw.rect(screen, ui_theme.YELLOW_MUTED, (icon_x + 5*px, ind_y + 3*px, 1*px, 2*px))
                # legs
                pygame.draw.rect(screen, ui_theme.YELLOW_BORDER, (icon_x + 2*px, ind_y + 5*px, 1*px, 4*px))
                pygame.draw.rect(screen, ui_theme.YELLOW_BORDER, (icon_x + 4*px, ind_y + 5*px, 1*px, 4*px))
            else:
                # Crouching icon (short/wide pixelated figure)
                # head
                pygame.draw.rect(screen, ui_theme.YELLOW_BRIGHT, (icon_x + 2*px, ind_y + 2*px, 3*px, 2*px))
                # wider crouched torso
                pygame.draw.rect(screen, ui_theme.YELLOW, (icon_x + 1*px, ind_y + 4*px, 5*px, 2*px))
                # short bent legs
                pygame.draw.rect(screen, ui_theme.YELLOW_BORDER, (icon_x + 1*px, ind_y + 6*px, 2*px, 2*px))
                pygame.draw.rect(screen, ui_theme.YELLOW_BORDER, (icon_x + 4*px, ind_y + 6*px, 2*px, 2*px))
                # tiny arms
                pygame.draw.rect(screen, ui_theme.YELLOW_MUTED, (icon_x + 0*px, ind_y + 5*px, 1*px, 1*px))
                pygame.draw.rect(screen, ui_theme.YELLOW_MUTED, (icon_x + 6*px, ind_y + 5*px, 1*px, 1*px))

        if not current_key.startswith("till") and current_key != "customer":
            # Do not show movement directions or controls on till views or customer screen
            help_text = small_font.render(
                "WASD = move  |  Q/E = turn  |  Ctrl = crouch/stand  |  Shift+O = console  |  Shift+I = toggle hand icons (text default)",
                True,
                ui_theme.PANEL_HINT,
            )
            screen.blit(help_text, (20, win_h - 30))

        # --- Very minimal console box (shows recent print() output in fullscreen) ---
        # Bottom-left corner, tiny, only last few lines. Keeps the game clean.
        # Hidden by default; toggle with Shift+O.
        if show_console and hasattr(sys.stdout, "lines") and sys.stdout.lines:
            lines = sys.stdout.lines
            line_h = 14
            box_h = len(lines) * line_h + 4
            box_w = 480
            box_x = 8
            margin_below = 36 if current_key != "customer" else 6
            box_y = win_h - box_h - margin_below

            ui_theme.draw_panel(
                screen, (box_x, box_y, box_w, box_h),
                fill=ui_theme.CONSOLE_FILL,
                border=ui_theme.CONSOLE_BORDER,
                radius=4,
            )

            ty = box_y + 2
            for line in lines:
                txt = console_font.render(line[:72], True, ui_theme.CONSOLE_TEXT)
                screen.blit(txt, (box_x + 4, ty))
                ty += line_h

        # Send-grade modal (after send_order on till)
        if pending_send_items is not None:
            _draw_send_grade_popup(
                screen, font, small_font, win_w, win_h,
                pending_send_items, send_popup_selection,
                mx=mx, my=my, hover_grow=hover_grow, dt_seconds=dt_seconds)

        # --- Tooltip for hovered photo-button action (or top-nav / customer UI actions) ---
        # Mirrors the style and behaviour from the till_button_tool editor.
        if tooltip_text and pending_send_items is None:
            curr_mx, curr_my = pygame.mouse.get_pos()
            ui_theme.draw_tooltip(
                screen, tooltip_text, small_font, curr_mx, curr_my, win_w, win_h)

        # --- Mouse cursor: hand when over any clickable (photo buttons, top tabs, customer buttons, photo area) ---
        is_clickable = tooltip_text is not None
        if pending_send_items is not None:
            for rect, _grade in send_popup_option_rects:
                rx, ry, rw, rh = rect
                if rx <= mx < rx + rw and ry <= my < ry + rh:
                    is_clickable = True
                    break
        if photo_rect is not None and pending_send_items is None:
            bx, by, bw, bh = photo_rect
            if bx <= mx <= bx + bw and by <= my <= by + bh:
                is_clickable = True
        if is_clickable:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND)
        else:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)

        pygame.display.flip()

    pygame.quit()
    print("Bar movement demo exited cleanly.")


def run_bar_review_session() -> None:
    """Entry point called from the main CLI when reviewing a due 'bar' type card.

    - Loads all currently due cards that have content type "bar".
    - Uses their "response" field (the demand key) to drive customer orders
      while any remain.
    - On each customer FINISH (while not in practice mode):
        * Only demands that were actually on the customer's list and still due are reviewed.
        * Successful demands use the user's place/send self-grade; failed ones get Again.
        * Extras placed or sent that were not demanded are never reviewed.
        * Removes reviewed demands from the due pool.
    - When the last due bar card has been processed, shows
      "All cards reviewed. Exit or keep playing" and subsequent customers
      are generated from the button-derived BarGame list (practice mode,
      no further database writes or FSRS updates). See load_potential_orders() and
      NeuroMods/Bar/BarGame.nm (regenerated by src/bar/genOrders.py; weighted by type).
    - The normal pygame controls and customer UI remain available.
    - Closing the window or ESC returns to the CLI.
    """
    global _review_mode, _due_map, _practice_mode

    _review_mode = True
    _practice_mode = False
    _due_map = {}

    print("\n=== Bar review session started ===")

    # Load due bar cards from DB (response must match a key we can actually demand)
    try:
        from datetime import datetime, timezone
        from ..core.db import dbDataFrame, getAdaptData

        df = dbDataFrame()
        if not df.empty:
            now_iso = datetime.now(timezone.utc).isoformat()
            due_df = df[df["due"] <= now_iso]
            for aid in due_df.index:
                try:
                    full, content, _typ = getAdaptData(str(aid))
                    if content and content.get("type") == "bar":
                        resp = content.get("response")
                        demand_keys = {d["key"] for d in POSSIBLE_DEMANDS} if POSSIBLE_DEMANDS and isinstance(POSSIBLE_DEMANDS[0], dict) else set(POSSIBLE_DEMANDS)
                        if isinstance(resp, str) and resp in demand_keys:
                            _due_map[resp] = str(aid)
                except Exception:
                    continue
    except Exception as e:
        print("Warning: could not load due bar cards (DB/scheduler not available?):", e)
        print("Continuing in practice mode using the full possible list.")

    if _due_map:
        print(f"Found {len(_due_map)} due bar card(s). Customers will use these until exhausted.")
    else:
        print("No due bar cards. Starting practice mode with the full list of possible orders (weighted by type).")
        _practice_mode = True

    # Run the normal interactive game. The first _sample_next_demands() call inside
    # run_demo() will see the _due_map we just populated and behave accordingly.
    # All the grading logic lives in the FINISH handler.
    try:
        run_demo()
    finally:
        # Always clean up so that a later direct run_demo() is unaffected.
        _review_mode = False
        _due_map = {}
        _practice_mode = False
        print("=== Returned from bar review session to CLI ===")


if __name__ == "__main__":
    run_demo()
