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
- Persistent top-left BAR/FOOD overlay buttons + all other photo buttons now come from the editor tool (JSON)
- Click: print original image coords for hotspots
- D: debug overlay
- ESC: quit

The view graph now models multiple positions + north/south facing + stand/crouch
(where photos exist). This will be revised with your next set of images.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional
import random

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


def _sample_next_demands():
    """Choose 3-6 demands. While there are still due bar cards in review mode,
    prefer sampling from the remaining due ones. Falls back to full POSSIBLE list.
    """
    global _review_mode, _due_map, _practice_mode
    if _review_mode and _due_map:
        keys = list(_due_map.keys())
        k = min(len(keys), random.randint(3, 6))
        if k > 0:
            return random.sample(keys, k=k)
    return random.sample(POSSIBLE_DEMANDS, k=random.randint(3, 6))



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
    image_path: str          # relative to the Bar root, e.g. "Bar Images/1N1.jpg" or "Till Images/bar till - bar screen.jpg"
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
# Spot 1 N/S specially wired to till_n. New views start clean (no buttons).

VIEWS: Dict[str, View] = {
    # === North facing (stand) - previous a-series + till ===
    "till_n": View(
        key="till_n",
        image_path="Till Images/bar till - bar screen.jpg",
        name="Till (west-most, north stand)",
        neighbors={
            "left": None,
            "right": "1N1",
            "forward": "customer",
            "back": None,
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
        neighbors={'left': 'till_n', 'right': '2N0', 'forward': None, 'back': None, 'turn_left': '1W0', 'turn_right': None, 'crouch': None, 'stand': '1N1'},
    ),
    "1N1": View(
        key="1N1",
        image_path="Bar Images/1N1.jpg",
        name="Spot 1 facing N (height 1)",
        neighbors={'left': 'till_n', 'right': '2N1', 'forward': None, 'back': None, 'turn_left': None, 'turn_right': '1E1', 'crouch': '1N0', 'stand': None},
    ),
    "1S0": View(
        key="1S0",
        image_path="Bar Images/1S0.jpg",
        name="Spot 1 facing S (height 0)",
        neighbors={'left': '2S0', 'right': None, 'forward': None, 'back': None, 'turn_left': 'till_n', 'turn_right': 'till_n', 'crouch': None, 'stand': None},
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
        neighbors={'left': None, 'right': None, 'forward': None, 'back': '2W0', 'turn_left': None, 'turn_right': '1N0', 'crouch': None, 'stand': '1W1'},
    ),
    "1W1": View(
        key="1W1",
        image_path="Bar Images/1W1.jpg",
        name="Spot 1 facing W (height 1)",
        neighbors={'left': None, 'right': None, 'forward': None, 'back': '2W1', 'turn_left': None, 'turn_right': '1N1', 'crouch': '1W0', 'stand': None},
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
    # Clicking tabs on the main till_n screen switches to these.
    # Clicking in a sub-menu returns to till_n (see click handling).
    "till_lager": View(
        key="till_lager",
        image_path="Till Images/bar till drinks - lager and cider.jpg",
        name="Till Submenu: Lager + Cider",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "till_bitter": View(
        key="till_bitter",
        image_path="Till Images/bar till drinks - bitter and ale.jpg",
        name="Till Submenu: Bitter + Ale",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "till_soft": View(
        key="till_soft",
        image_path="Till Images/bar till drinks - soft.jpg",
        name="Till Submenu: Softs",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "till_spirits": View(
        key="till_spirits",
        image_path="Till Images/bar till drinks - spirits.jpg",
        name="Till Submenu: Spirits",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "till_wine": View(
        key="till_wine",
        image_path="Till Images/bar till drinks - wine.jpg",
        name="Till Submenu: Wine",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "till_bottles": View(
        key="till_bottles",
        image_path="Till Images/bar till drinks - bottles.jpg",
        name="Till Submenu: Bottles",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "till_crisps": View(
        key="till_crisps",
        image_path="Till Images/bar till drinks - crisps.jpg",
        name="Till Submenu: Crisps",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "till_kids": View(
        key="till_kids",
        image_path="Till Images/bar till drinks - kids.jpg",
        name="Till Submenu: Kids Drinks",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "till_promo": View(
        key="till_promo",
        image_path="Till Images/bar till drinks - drink promo.jpg",
        name="Till Submenu: Drink Promo",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),

    # === Till food menu views (home + subs) ===
    "till_food": View(
        key="till_food",
        image_path="Till Images/bar till - food screen.jpg",
        name="Till Food Screen (home)",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "till_food_burgers": View(
        key="till_food_burgers",
        image_path="Till Images/bar till food - burgers.jpg",
        name="Till Food: Burgers",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "till_food_carvery": View(
        key="till_food_carvery",
        image_path="Till Images/bar till food - carvery.jpg",
        name="Till Food: Carvery",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "till_food_sides": View(
        key="till_food_sides",
        image_path="Till Images/bar till food - sides.jpg",
        name="Till Food: Sides",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "till_food_meat_free": View(
        key="till_food_meat_free",
        image_path="Till Images/bar till food - meat free.jpg",
        name="Till Food: Meat Free",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "till_food_desserts": View(
        key="till_food_desserts",
        image_path="Till Images/bar till food - desserts.jpg",
        name="Till Food: Desserts",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "till_food_kids_food": View(
        key="till_food_kids_food",
        image_path="Till Images/bar till food - kids.jpg",
        name="Till Food: Kids",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "till_food_meal_deal": View(
        key="till_food_meal_deal",
        image_path="Till Images/bar till menu - meal deal.jpg",
        name="Till Food: Meal Deal",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    "till_food_promo": View(
        key="till_food_promo",
        image_path="Till Images/bar till food - food promo.jpg",
        name="Till Food: Food Promo",
        neighbors={"left": None, "right": None, "forward": None, "back": None, "turn_left": None, "turn_right": None, "crouch": None, "stand": None},
    ),
    # Customer screen - accessed by 'forward' from till_n (looking up from the till towards the customer)
    # No left/right/turn/crouch from here. Only back to till.
    # Blank for now with placeholder text box for customer demands.
    "customer": View(
        key="customer",
        image_path=None,  # special blank screen, drawn manually
        name="Customer",
        neighbors={
            "left": None,
            "right": None,
            "forward": None,
            "back": "till_n",
            "turn_left": None,
            "turn_right": None,
            "crouch": None,
            "stand": None,
        },
    ),
}

# Keys to preload (order doesn't matter much for graph navigation)
VIEW_ORDER = list(VIEWS.keys())

# (TILL_BAR_TABS and TILL_FOOD_TABS removed - all buttons now come from the editor tool via JSON)

# Back button area for submenu screens (top right, approximate)
TILL_SUB_BACK_RECT = (2750, 60, 360, 110)

# Persistent top-left navigation for till interface (drawn in screen coordinates)
# Always available when in any till_* view.
TILL_TOP_BAR_RECT = (30, 20, 180, 55)   # switches to bar home (till_n)
TILL_TOP_FOOD_RECT = (230, 20, 180, 55) # switches to food home (till_food)

# Customer screen UI buttons (screen coordinates)
# The 4 grade buttons (Again/Hard/Good/Easy) replace the old single PLACE action.
# They place the item from the right hand and record the user-chosen grade for placed items.
# "PLACE" label is drawn above the first grade button.
GRADE_AGAIN_RECT = (950, 265, 220, 38)
GRADE_HARD_RECT  = (950, 306, 220, 38)
GRADE_GOOD_RECT  = (950, 347, 220, 38)
GRADE_EASY_RECT  = (950, 388, 220, 38)
RESET_BUTTON_RECT = (950, 435, 220, 40)
FINISH_BUTTON_RECT = (950, 480, 220, 40)
PLACED_ITEMS_BOX = (20, 50, 300, 300)  # text box for placed list on LEFT side
SENT_ITEMS_BOX = (960, 50, 300, 180)  # text box for sent from till on right side (shorter to fit buttons below)

# Possible customer demands: things that can be taken (glasses + specific drink brands via take buttons)
# and specific food/drink items that can be sent from the till sub-menus (the actual selectable items, not the category sub-menu names themselves).
# Update this list (using the raw keys from your take: and send buttons) whenever you add more via the editor tool.
POSSIBLE_DEMANDS = [
    # All items currently available via take: buttons in till_buttons.json
    # (extracted directly from the JSON to avoid hallucinations)
    "JJ_london",
    "Jimador_blanco",
    "Madri_glass",
    "antica_classic",
    "antica_liquorice",
    "antica_raspberry",
    "doombar_glass",
    "guiness_glass",
    "jack_daniels",
    "jagermeister",
    "jimador_reposado",
    "martini",
    "red_campo_viejo",
    "red_finca_del_alta_malbec",
    "red_flagstone_poetry",
    "red_gut_oggau",
    "red_jam_shed_shiraz",
    "red_matinal_merlot",
    "rose_vino_pomona_pinot_grigio",
    "tequila_rose",
    "vina_arroba_tempranillo",
    "white_andrew_peace_silhouette",
    "white_jack_rabbit_pinot_grigio",
    "white_jam_shed_chardonnay",
    "white_matinal_sauvignon_blanc",
    "white_ned_sauvignon_blanc",
    "whitley_black_cherry",
    "whitley_raspberry",
    # Burgers from add_order: buttons in the food sub-menus (the actual items, not the sub-menu tabs)
    "BGR_Big_Stack",
    "BGR_Bombay",
    "BGR_Chs_Bcn",
    "BGR_Korean",
    "BGR_Korean_grilled",
    "BGR_Vegan",
]

def format_demand(demand: str) -> str:
    """Format raw demand key (from take: actions) to nice display name.
    Removes underscores, applies title case, fixes common brand spellings,
    and adds 'a' or 'an'.
    """
    name = demand.replace('_', ' ').title()

    # Brand and name fixes (expand as you add more via the tool)
    fixes = {
        'Guiness Glass': 'Guinness Glass',
        'Jimador Blanco': 'El Jimador Blanco',
        'Jimador Reposado': 'El Jimador Reposado',
        'Jj London': 'JJ London',
        'Antica Classic': 'Antica Classic',
        'Antica Liquorice': 'Antica Liquorice',
        'Antica Raspberry': 'Antica Raspberry',
        'Doombar Glass': 'Doom Bar Glass',
        'Madri Glass': 'Madri Glass',
        'Jack Daniels': "Jack Daniel's",
        'Jagermeister': 'Jägermeister',
        'Martini': 'Martini',
        'Tequila Rose': 'Tequila Rose',
        'Red Campo Viejo': 'Campo Viejo Red',
        'Red Finca Del Alta Malbec': 'Finca del Alta Malbec',
        'Red Flagstone Poetry': 'Flagstone Poetry',
        'Red Gut Oggau': 'Gut Oggau',
        'Red Jam Shed Shiraz': 'Jam Shed Shiraz',
        'Red Matinal Merlot': 'Matinal Merlot',
        'Rose Vino Pomona Pinot Grigio': 'Vino Pomona Pinot Grigio Rosé',
        'Vina Arroba Tempranillo': 'Viña Arroba Tempranillo',
        'White Andrew Peace Silhouette': 'Andrew Peace Silhouette',
        'White Jack Rabbit Pinot Grigio': 'Jack Rabbit Pinot Grigio',
        'White Jam Shed Chardonnay': 'Jam Shed Chardonnay',
        'White Matinal Sauvignon Blanc': 'Matinal Sauvignon Blanc',
        'White Ned Sauvignon Blanc': 'Ned Sauvignon Blanc',
        'Whitley Black Cherry': 'Whitley Black Cherry',
        'Whitley Raspberry': 'Whitley Raspberry',
        'Bgr Big Stack': 'BGR Big Stack',
        'Bgr Bombay': 'BGR Bombay',
        'Bgr Chs Bcn': 'BGR Cheese + Bacon',
        'Bgr Korean': 'BGR Korean',
        'Bgr Korean Grilled': 'BGR Korean Grilled',
        'Bgr Vegan': 'BGR Vegan',
    }
    for old, new in fixes.items():
        name = name.replace(old, new)

    # Add article
    if name and name[0].lower() in 'aeiou':
        name = 'an ' + name
    else:
        name = 'a ' + name
    return name

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
# The actual demo
# ---------------------------------------------------------------------------

def run_demo() -> None:
    """Launch the interactive bar explorer demo."""
    global pygame
    if pygame is None:
        import pygame as _pygame
        pygame = _pygame

    images_dir = _get_bar_images_root()
    print(f"Using images from: {images_dir} (Bar Images/ + Till Images/)")

    # Order system for till interactions (bar drinks + food items)
    orders = []

    # Right hand state for take actions (e.g. holding a glass)
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

    # Message after finish
    finish_message = ""

    # Mapping for beer glass demands to the drink name sent from till
    BEER_GLASS_TO_DRINK = {
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

    # Helpful startup info for the current layout
    print("\n=== Current known layout (new Bar Images/ SpotDirH photos) ===")
    print("Spots 1(west)-7(east). Keys: e.g. 1N1=spot1 North stand, 7S0=spot7 South crouch.")
    print("Till at west of spot 1. Customer forward from till_n.")
    print()
    print("Controls:")
    print("  W / S (or Up/Down) : forward / back (along facing, esp. useful for E/W facings)")
    print("  A / D              : left / right from player's perspective (for N/S: along bar)")
    print("  Left/Right arrows  : absolute west / east on the bar")
    print("  Q / E              : turn left / turn right")
    print("  Ctrl (or C)        : toggle between crouch and stand (when relevant for the current view)")
    print("  Top BAR/FOOD + photo buttons : click to switch menus or add items to order")
    print("  To visually design buttons   : run  python -m src.bar.till_button_tool")
    print("  Buttons are loaded from      : NeuroMods/Bar/till_buttons.json")
    print("  D                  : toggle debug (shows button boxes + neighbor info)")
    print("  ESC                : quit (or return from till sub-menu)")
    print("============================================================================\n")

    pygame.init()
    pygame.display.set_caption("Adapt Bar Trainer — Movement Prototype (ESC to quit)")

    # A comfortable development size. You can make it bigger or resizable later.
    WINDOW_SIZE = (1280, 720)
    screen = pygame.display.set_mode(WINDOW_SIZE)
    clock = pygame.time.Clock()

    # Pre-load a couple of surfaces (lazy loading is also fine)
    surface_cache: Dict[str, pygame.Surface] = {}
    original_sizes: Dict[str, tuple[int, int]] = {}

    for key in VIEW_ORDER:
        if key == "customer":
            surface_cache[key] = None  # special blank screen
            original_sizes[key] = (0, 0)
            continue
        view = get_view(key)
        surf = load_image_surface(view, images_dir)
        surface_cache[key] = surf
        original_sizes[key] = surf.get_size()
        print(f"  Loaded {key}: {original_sizes[key][0]}x{original_sizes[key][1]}")

    current_key = "till_n"  # Start on the north side at the till (west-most)
    font = pygame.font.SysFont(None, 28)
    small_font = pygame.font.SysFont(None, 20)

    show_debug = True  # press D to toggle

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                TILL_HOMES = ("till_n", "till_food")
                if event.key == pygame.K_ESCAPE:
                    if current_key.startswith("till_") and current_key not in TILL_HOMES:
                        if "food" in current_key:
                            current_key = "till_food"
                        else:
                            current_key = "till_n"
                    else:
                        running = False
                    continue

                if current_key.startswith("till_") and current_key not in TILL_HOMES:
                    # In till sub-menu: ignore bar movement/turn/crouch keys
                    # (only escape handled above; clicks handle returning)
                    continue

                if current_key == "till_n":
                    if event.key in (pygame.K_w, pygame.K_UP):
                        view = get_view(current_key)
                        nxt = view.go("forward")
                        if nxt:
                            current_key = nxt
                            print("Facing the customer")
                        else:
                            print("  [No view forward from here]")
                        continue

                if current_key == "customer":
                    if event.key in (pygame.K_s, pygame.K_DOWN, pygame.K_b):
                        view = get_view(current_key)
                        nxt = view.go("back")
                        if nxt:
                            current_key = nxt
                            print("Back to the till")
                        continue
                    # No left, right, turning, or crouch/stand capability from customer screen
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

                elif event.key == pygame.K_d:
                    show_debug = not show_debug
                    print(f"Debug overlays: {'ON' if show_debug else 'OFF'}")

                elif event.key == pygame.K_F1:
                    # Future: help overlay
                    print("F1 pressed — (future: show controls + current view hotspots)")

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # Left click — report position in original image pixels
                mx, my = event.pos

                # Top nav (BAR / FOOD) + SEND are in screen coordinates and always checked first for any till view
                top_nav_handled = False
                if current_key.startswith("till"):
                    if mx >= TILL_TOP_BAR_RECT[0] and mx < TILL_TOP_BAR_RECT[0] + TILL_TOP_BAR_RECT[2] and \
                       my >= TILL_TOP_BAR_RECT[1] and my < TILL_TOP_BAR_RECT[1] + TILL_TOP_BAR_RECT[3]:
                        current_key = "till_n"
                        print("Switched to Bar menu (home)")
                        top_nav_handled = True
                    elif mx >= TILL_TOP_FOOD_RECT[0] and mx < TILL_TOP_FOOD_RECT[0] + TILL_TOP_FOOD_RECT[2] and \
                       my >= TILL_TOP_FOOD_RECT[1] and my < TILL_TOP_FOOD_RECT[1] + TILL_TOP_FOOD_RECT[3]:
                        current_key = "till_food"
                        print("Switched to Food menu (home)")
                        top_nav_handled = True
                    # (SEND ORDER is now handled via TILL_PHOTO_BUTTON_DATA / the editor tool)
                if top_nav_handled:
                    continue  # skip image coord processing for this click

                if current_key == "customer":
                    # Handle grade buttons (these replace the old single PLACE).
                    # Clicking a grade while holding something in right hand "places" it
                    # and records the user's self-reported ease of recall (for placed items in review).
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
                            if right_hand:
                                placed.append(right_hand)
                                placed_grades[right_hand] = g
                                print(f"Placed {right_hand} on the counter (user grade={g}).")
                                right_hand = None
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
                    if (FINISH_BUTTON_RECT[0] <= mx < FINISH_BUTTON_RECT[0] + FINISH_BUTTON_RECT[2] and
                        FINISH_BUTTON_RECT[1] <= my < FINISH_BUTTON_RECT[1] + FINISH_BUTTON_RECT[3]):
                        # Compute success per demand using the exact rules:
                        # - beer (glass demands): BOTH glass placed AND matching drink sent from till
                        # - burger: only sent from till
                        # - other (wine/spirit/etc): only placed by customer
                        total = len(current_demands)
                        success = 0
                        succeeded = set()
                        for demand in current_demands:
                            ok = False
                            if demand in BEER_GLASS_TO_DRINK:
                                drink = BEER_GLASS_TO_DRINK[demand]
                                if drink in sent_orders and demand in placed:
                                    ok = True
                            elif demand in BURGER_DEMANDS:
                                if demand in sent_orders:
                                    ok = True
                            else:
                                # other drink: only needs to be placed
                                if demand in placed:
                                    ok = True
                            if ok:
                                success += 1
                                succeeded.add(demand)

                        finish_message = f"{success}/{total} orders were successful"
                        print("=== CUSTOMER FINISHED ===")
                        print(finish_message)

                        # --- Bar review / FSRS integration ---
                        # Only demands the customer actually asked for (in current_demands) get reviewed.
                        # - If a demanded item was NOT correctly fulfilled (missing what was asked):
                        #     force grade=1 (Again). Mistakes always cost the lowest grade.
                        # - If correctly fulfilled (placed/sent per the rules for beer/burger/other):
                        #     use the user-defined grade from the place-grade buttons or the new send-grade
                        #     buttons (Easy/Good/Hard/Again) if one was assigned for that item.
                        #     This lets the user rate how hard it was to find/recall the item (even if correct).
                        # - Extras the user sent/placed that the customer did NOT ask for are not reviewed
                        #   (their grades are recorded but ignored for FSRS, since we only look at demanded items).
                        if _review_mode:
                            for demand in list(current_demands):
                                if demand in _due_map:
                                    if demand not in succeeded:
                                        # missing what customer asked -> Again (1), regardless of any grade assigned
                                        grade = 1
                                    else:
                                        # correctly placed/sent for this demand -> prefer user grade (place or send)
                                        if demand in placed_grades:
                                            grade = placed_grades[demand]
                                        elif demand in sent_grades:
                                            grade = sent_grades[demand]
                                        else:
                                            grade = 3  # correct but no user grade given -> default Good
                                    adapt_id = _due_map.pop(demand)
                                    try:
                                        from ..core.db import getAdaptData, updateDB
                                        from ..core.scheduler import schedulerReview
                                        full, _, _ = getAdaptData(adapt_id)
                                        if full:
                                            sched_dict, new_due = schedulerReview(full, grade=grade)
                                            updateDB(adapt_id=adapt_id, scheduling_dict=sched_dict, newDue=new_due)
                                            print(f"  [review] {demand} -> grade {grade} (adapt_id={adapt_id})")
                                    except Exception as ex:
                                        print(f"  [review] FSRS update error for {demand}: {ex}")

                            if not _due_map and not _practice_mode:
                                _practice_mode = True
                                finish_message += "   All cards reviewed. Exit or keep playing."

                        # Clear states for new customer, generate new demands, stay on customer screen
                        placed.clear()
                        placed_grades.clear()
                        sent_orders.clear()
                        sent_grades.clear()
                        right_hand = None
                        current_demands = _sample_next_demands()
                        print("A new customer has arrived with fresh demands!")
                        continue
                    # Other clicks on customer screen: ignore for now
                    continue

                view = get_view(current_key)
                orig_w, orig_h = original_sizes.get(current_key, (3160, 1815))

                # We need the current scaled + blit position.
                # Recompute it here (cheap) so we don't have to store it.
                current_surf = surface_cache[current_key]
                scaled, (bx, by) = scale_and_center(current_surf, WINDOW_SIZE)
                sw, sh = scaled.get_size()

                ix, iy = screen_to_image_coords(mx, my, bx, by, sw, sh, orig_w, orig_h)

                if ix >= 0:
                    # Always check tool-created photo buttons for current view (now supports all images: till + glasses/positions)
                    btns = TILL_PHOTO_BUTTON_DATA.get(current_key, [])
                    button_handled = False
                    for btn in btns:
                        tx, ty, tw, th = btn["rect"]
                        if tx <= ix < tx + tw and ty <= iy < ty + th:
                            action = btn.get("action", "")
                            if ":" in action:
                                prefix, value = action.split(":", 1)
                                value = value.strip()
                                if prefix == "add_order":
                                    orders.append(value)
                                    print(f"Added to order: {value}")
                                elif prefix in ("switch", "go_to"):
                                    if value in VIEWS:
                                        current_key = value
                                        print(f"Switched to till screen: {value}")
                                    else:
                                        print(f"Invalid switch target: {value}")
                                elif prefix == "take":
                                    right_hand = value
                                    print(f"Took {value} into right hand (overwrote previous).")
                            elif action == "send_order":
                                if orders:
                                    sent_orders.extend(orders)
                                    print("=== SENDING ORDER ===")
                                    for item in orders:
                                        print(f"  - {item}")
                                    print("Order sent to kitchen!")
                                    orders.clear()
                                else:
                                    print("No items in current order.")
                            else:
                                # Support for split Send button: top is just "Send" text (no action or unknown),
                                # lower 4 parts use sendAgain/sendHard/sendGood/sendEasy (or variants)
                                # to send the orders AND record a user grade for the sent items.
                                send_grade = None
                                if action == "send_order":
                                    send_grade = 3  # legacy default
                                elif action in SEND_GRADE_MAP:
                                    send_grade = SEND_GRADE_MAP[action]
                                if send_grade is not None:
                                    if orders:
                                        sent_orders.extend(orders)
                                        for item in orders:
                                            sent_grades[item] = send_grade
                                        print("=== SENDING ORDER ===")
                                        for item in orders:
                                            print(f"  - {item} (user grade {send_grade})")
                                        print("Order sent to kitchen!")
                                        orders.clear()
                                    else:
                                        print("No items in current order.")
                            button_handled = True

                    if not button_handled:
                        if current_key.startswith("till_"):
                            # Legacy back rect for submenus (top nav is preferred way now)
                            bx1, by1, bw, bh = TILL_SUB_BACK_RECT
                            if bx1 <= ix < bx1 + bw and by1 <= iy < by1 + bh:
                                if "food" in current_key:
                                    current_key = "till_food"
                                else:
                                    current_key = "till_n"
                                print("Returned to menu home")
                            else:
                                print(f"Clicked in submenu '{current_key}' at ({ix}, {iy}) "
                                      f"(future: select/ring item)  [use top BAR/FOOD or back rect to return]")
                        elif not current_key.startswith("till"):
                            # For non-till views (e.g. position photos), print coords if no button hit (for further editing)
                            print(f"Click on '{current_key}' at original pixels: ({ix}, {iy})  "
                                  f"[screen=({mx},{my})]")
                else:
                    print(f"Click outside photo area on '{current_key}'")

        # ---------------- Rendering ----------------
        screen.fill((20, 20, 25))  # dark background for letterboxing

        if current_key == "customer":
            # Blank customer screen with text boxes and buttons
            # No photo, just placeholder UI
            # Ensure no overlaps: demands center, placed LEFT, sent RIGHT upper, buttons RIGHT lower

            # Demands box in center (moved slightly to avoid overlaps)
            dem_w, dem_h = 580, 180
            dem_x = (WINDOW_SIZE[0] - dem_w) // 2
            dem_y = 40
            pygame.draw.rect(screen, (30, 30, 40), (dem_x, dem_y, dem_w, dem_h))
            pygame.draw.rect(screen, (180, 180, 180), (dem_x, dem_y, dem_w, dem_h), 2)

            # Auto-generated customer demands (3-6 items from takeables and sendables)
            formatted_demands = [format_demand(d) for d in current_demands]
            demands = ["Customer demands:"] + [""] + [f"• {d}" for d in formatted_demands] + [
                "",
                "Click a grade button (Again/Hard/Good/Easy) to place the item in your right hand",
                "and rate how easy it was to recall/find. Press FINISH when done."
            ]
            y = dem_y + 12
            for line in demands:
                txt = small_font.render(line, True, (255, 255, 200))
                screen.blit(txt, (dem_x + 12, y))
                y += 18

            # Placed items text box on LEFT side
            pygame.draw.rect(screen, (30, 30, 40), PLACED_ITEMS_BOX)
            pygame.draw.rect(screen, (180, 180, 180), PLACED_ITEMS_BOX, 2)
            py = PLACED_ITEMS_BOX[1] + 10
            ptxt = small_font.render("Placed on counter:", True, (255, 255, 200))
            screen.blit(ptxt, (PLACED_ITEMS_BOX[0] + 8, py))
            py += 20
            if placed:
                for item in placed:
                    g = placed_grades.get(item)
                    label = f"- {format_demand(item)}"
                    if g is not None:
                        label += f" [{g}]"
                    itxt = small_font.render(label, True, (255, 255, 255))
                    screen.blit(itxt, (PLACED_ITEMS_BOX[0] + 8, py))
                    py += 16
            else:
                itxt = small_font.render("(none)", True, (180, 180, 180))
                screen.blit(itxt, (PLACED_ITEMS_BOX[0] + 8, py))

            # Sent from till text box on RIGHT side (upper)
            pygame.draw.rect(screen, (30, 30, 40), SENT_ITEMS_BOX)
            pygame.draw.rect(screen, (180, 180, 180), SENT_ITEMS_BOX, 2)
            py = SENT_ITEMS_BOX[1] + 10
            stxt = small_font.render("Sent from till:", True, (255, 255, 200))
            screen.blit(stxt, (SENT_ITEMS_BOX[0] + 8, py))
            py += 20
            if sent_orders:
                for item in sent_orders:
                    itxt = small_font.render(f"- {format_demand(item)}", True, (255, 255, 255))
                    screen.blit(itxt, (SENT_ITEMS_BOX[0] + 8, py))
                    py += 16
            else:
                itxt = small_font.render("(none)", True, (180, 180, 180))
                screen.blit(itxt, (SENT_ITEMS_BOX[0] + 8, py))

            # Buttons on right side (lower, below sent box to avoid overlap)
            # "PLACE" label above the grade buttons (user request)
            place_label = small_font.render("PLACE", True, (255, 220, 100))
            place_label_x = 950 + (220 - place_label.get_width()) // 2
            place_label_y = 265 - 22  # just above the "Again" button
            screen.blit(place_label, (place_label_x, place_label_y))

            # 4 grade buttons. These place the current right_hand item and record the user's
            # self-grade for recall difficulty (used for placed demands in review mode).
            grade_buttons = [
                (GRADE_AGAIN_RECT, "Again"),
                (GRADE_HARD_RECT, "Hard"),
                (GRADE_GOOD_RECT, "Good"),
                (GRADE_EASY_RECT, "Easy"),
            ]
            for rect, label in grade_buttons:
                pygame.draw.rect(screen, (0, 0, 0), rect)
                gtxt = small_font.render(label, True, (255, 255, 255))
                gx = rect[0] + (rect[2] - gtxt.get_width()) // 2
                gy = rect[1] + (rect[3] - gtxt.get_height()) // 2
                screen.blit(gtxt, (gx, gy))

            # Reset placed button
            pygame.draw.rect(screen, (0, 0, 0), RESET_BUTTON_RECT)
            reset_txt = small_font.render("RESET PLACED", True, (255, 255, 255))
            rx = RESET_BUTTON_RECT[0] + (RESET_BUTTON_RECT[2] - reset_txt.get_width()) // 2
            ry = RESET_BUTTON_RECT[1] + (RESET_BUTTON_RECT[3] - reset_txt.get_height()) // 2
            screen.blit(reset_txt, (rx, ry))

            # Finish button
            pygame.draw.rect(screen, (0, 0, 0), FINISH_BUTTON_RECT)
            finish_txt = small_font.render("FINISH", True, (255, 255, 255))
            fx = FINISH_BUTTON_RECT[0] + (FINISH_BUTTON_RECT[2] - finish_txt.get_width()) // 2
            fy = FINISH_BUTTON_RECT[1] + (FINISH_BUTTON_RECT[3] - finish_txt.get_height()) // 2
            screen.blit(finish_txt, (fx, fy))

            # The right hand box will also show here (non-till view)

            # Finish message box at the bottom (only after finish, for the previous customer)
            if finish_message:
                msg_surf = small_font.render(finish_message, True, (255, 255, 100))
                msg_w = msg_surf.get_width() + 20
                msg_h = 30
                msg_x = (WINDOW_SIZE[0] - msg_w) // 2
                msg_y = WINDOW_SIZE[1] - 70
                pygame.draw.rect(screen, (50, 50, 30), (msg_x, msg_y, msg_w, msg_h))
                pygame.draw.rect(screen, (200, 200, 100), (msg_x, msg_y, msg_w, msg_h), 1)
                screen.blit(msg_surf, (msg_x + 10, msg_y + 5))
        else:
            current_view = get_view(current_key)
            current_surf = surface_cache[current_key]

            scaled, (bx, by) = scale_and_center(current_surf, WINDOW_SIZE)
            screen.blit(scaled, (bx, by))

        # Draw top navigation (BAR / FOOD) - always visible in till mode (screen coords for consistency)
        if current_key.startswith("till"):
            # Draw in fixed screen positions (top left)
            pygame.draw.rect(screen, (0, 100, 255), TILL_TOP_BAR_RECT, 3)
            bar_label = small_font.render("BAR", True, (0, 100, 255))
            screen.blit(bar_label, (TILL_TOP_BAR_RECT[0] + 10, TILL_TOP_BAR_RECT[1] + 10))

            pygame.draw.rect(screen, (255, 100, 0), TILL_TOP_FOOD_RECT, 3)
            food_label = small_font.render("FOOD", True, (255, 100, 0))
            screen.blit(food_label, (TILL_TOP_FOOD_RECT[0] + 10, TILL_TOP_FOOD_RECT[1] + 10))

        # (Left category tabs removed - now managed via the till_button_tool + JSON for all photo buttons)

        # Draw photo-space buttons from the editor tool (TILL_PHOTO_BUTTON_DATA)
        # Works for any view (till screens + position/glass images)
        if current_key in original_sizes and current_key != "customer":
            orig_w, orig_h = original_sizes[current_key]
            img_w, img_h = scaled.get_size()
            x_scale = img_w / orig_w
            y_scale = img_h / orig_h

            btns = TILL_PHOTO_BUTTON_DATA.get(current_key, [])
            for btn in btns:
                tx, ty, tw, th = btn["rect"]
                sx = bx + int(tx * x_scale)
                sy = by + int(ty * y_scale)
                sw = int(tw * x_scale)
                sh = int(th * y_scale)

                color_name = btn.get("color", "blue")
                rgb = _BUTTON_COLORS.get(color_name, (0, 0, 0))

                if color_name == "transparent black":
                    s = pygame.Surface((sw, sh), pygame.SRCALPHA)
                    s.fill((0, 0, 0, 128))  # semi-transparent black
                    screen.blit(s, (sx, sy))
                    text_color = (255, 255, 255)
                else:
                    pygame.draw.rect(screen, rgb, (sx, sy, sw, sh))
                    text_color = (0, 0, 0) if color_name != "black" else (255, 255, 255)

                # Center the text in the button
                label_surf = small_font.render(btn.get("label", "?"), True, text_color)
                text_x = sx + (sw - label_surf.get_width()) // 2
                text_y = sy + (sh - label_surf.get_height()) // 2
                screen.blit(label_surf, (text_x, text_y))

        # Small placeholder text box showing right hand (for take actions on glasses etc.)
        # Only in non-till views (the actual bar positions), bottom-right, slightly higher to clear help text.
        if not current_key.startswith("till"):
            hand_text = f"Right hand: {right_hand if right_hand else 'empty'}"
            hand_surf = small_font.render(hand_text, True, (255, 255, 200))
            box_w = hand_surf.get_width() + 10
            box_h = hand_surf.get_height() + 6
            x = WINDOW_SIZE[0] - box_w - 15
            y = WINDOW_SIZE[1] - 55  # slightly higher than bottom to avoid obstructing help text at -30
            pygame.draw.rect(screen, (40, 40, 50), (x, y, box_w, box_h))
            pygame.draw.rect(screen, (100, 100, 100), (x, y, box_w, box_h), 1)
            screen.blit(hand_surf, (x + 5, y + 3))

        # Overlay info
        # Ensure current_view is always defined (customer view is special-cased for UI)
        current_view = get_view(current_key)
        label = font.render(f"{current_view.name}   (key: {current_key})", True, (255, 255, 200))
        screen.blit(label, (20, 20))

        if current_key != "customer":
            # Do not show movement directions (left/right/turn etc.) on the customer screen
            help_text = small_font.render(
                "A/D = move (rel. to facing)  |  ←/→ = move (abs. west/east)  |  Q/E = turn  |  Ctrl (or C) = toggle crouch/stand  |  Top BAR/FOOD + in-photo buttons  |  Run till_button_tool.py to visually add/edit  |  D=debug  |  ESC=quit",
                True,
                (180, 180, 180),
            )
            screen.blit(help_text, (20, WINDOW_SIZE[1] - 30))

        if show_debug and current_key != "customer":
            # Show the full neighbor map for the current view (very useful while
            # we design the layout and add crouch/turn states).
            # Hidden on customer screen per user request (hides "back: None", "crouch: None", etc.)
            neigh = current_view.neighbors
            debug_lines = [f"{dir}: {neigh.get(dir)}" for dir in neigh]
            y = 55
            for line in debug_lines:
                txt = small_font.render(line, True, (100, 200, 255))
                screen.blit(txt, (20, y))
                y += 18

            # Draw a thin border around the photo area so it's obvious
            sw, sh = scaled.get_size()
            pygame.draw.rect(screen, (80, 80, 100), (bx, by, sw, sh), 1)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    print("Bar movement demo exited cleanly.")


def run_bar_review_session() -> None:
    """Entry point called from the main CLI when reviewing a due 'bar' type card.

    - Loads all currently due cards that have content type "bar".
    - Uses their "response" field (the demand key) to drive customer orders
      while any remain.
    - On each customer FINISH:
        * For demands that were due: successful ones get FSRS grade=3,
          unsuccessful ones get grade=2 (updates S/R/due in DB via schedulerReview + updateDB).
        * Removes them from the due pool.
    - When the last due bar card has been processed, shows
      "All cards reviewed. Exit or keep playing" and subsequent customers
      are generated from the full static POSSIBLE_DEMANDS list (practice mode,
      no further database writes or FSRS updates).
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
                        if isinstance(resp, str) and resp in POSSIBLE_DEMANDS:
                            _due_map[resp] = str(aid)
                except Exception:
                    continue
    except Exception as e:
        print("Warning: could not load due bar cards (DB/scheduler not available?):", e)
        print("Continuing in practice mode using the full possible list.")

    if _due_map:
        print(f"Found {len(_due_map)} due bar card(s). Customers will use these until exhausted.")
    else:
        print("No due bar cards. Starting practice mode with the full list of possible orders.")
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
