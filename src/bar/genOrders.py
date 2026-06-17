#!/usr/bin/env python3
"""
Script to generate the list of "potential orders" for the bar trainer.

A potential order is an item for which there exists:
  - A way to order/send it (via an order:ZZZ button)
  - AND (unless it's a food item i.e. order:food*), a way to acquire it (take:/pour: button)

Food items only require the order: button (they are sent to kitchen, not acquired at bar).

The "name" (the part after "take:", "pour:", or "order:") must be exactly the same string. No normalization is performed here — the button names in till_buttons.json are already the canonical names as set by the user.

This list is used for:
  - Customer demand generation in practice (non-review) mode
  - The static POSSIBLE_DEMANDS list (practice list)
  - Generating NeuroMods/Bar/potentialOrders.nm (structured: key|display_name|type|weight per line, importable)

Run this whenever you add/edit take:/pour:/order: buttons in the till button editor. (Module is now src.bar.genOrders)

Usage:
    python -m src.bar.genOrders
    # or from project root:
    python src/bar/genOrders.py

=== Display name, type and weight logic (FOOD ITEMS ONLY) ===
This logic is applied only to items where the order: name starts with "food" (after stripping "order:").

1. Start with the part after "order:"  (e.g. "foodBigstackBurger" or "foodChipsSide" or "foodKidsSTPoppinChicken")

2. Remove one matching prefix (try in this order, first match wins):
   - "foodKidsBY"
   - "foodKidsST"
   - "foodKids"
   - "food"

3. Remove trailing suffix if present (exactly):
   - "Side"
   - "Extra"
   (Do the prefix removal first, then suffix.)

4. Convert the result to a nice display name by inserting spaces before uppercase letters
   (e.g. "BigstackBurger" -> "Bigstack Burger", "PoppinChicken" -> "Poppin Chicken").

Type determination (after checking the original post-order: name):
  - if ends with "Side" -> "side"
  - elif ends with "Extra" -> "extra"
  - else (just food* prefix) -> "food"
  - For non-food: 
    - if the key exactly matches a beer BASE (guinessGlass, madriGlass etc. from take:), set to "emptyGlass"
    - else if the key is a Half/Full/Poured variant of beer BASE (e.g. madriGlassHalf, guinessGlassFull), set to "beer"
    - else if matches wine (take:red*/white*/rose* excl. redbull, or thimble variants *25/*50/*125), set to "wine"
    - else if matches additional empty glass (tallGlass etc.), set to "emptyGlass"
    - else "other"
  (wines and beers get weight 1.0; emptyGlass are excluded from potential orders)

Weight mapping (how likely a customer is to ask for it, used for weighted random selection in demand generation):
  - "food"  : 1.0
  - "side"  : 0.25
  - "extra" : 0.25
  - "other" : 1.0   (for all non-food items that have both take:/pour: + order:)
  - "wine"  : 1.0   (for wine items gotten via take:red*, take:white* or take:rose* , e.g. red wines, white wines, rosés; also thimble variants like redXXX25)
  - "beer"  : 1.0   (for Half/Full/Poured variants of beer glasses e.g. madriGlassHalf, guinessGlassFull)
  - "emptyGlass": 0   (for beer BASES like guinessGlass, madriGlass and other empty glasses like tallGlass; NEVER in potential orders)

Example:
  "order:foodBigstackBurger" -> ... -> display="Bigstack Burger", type="food", weight=1.0

  "order:foodChipsSide" -> ... -> display="Chips", type="side", weight=0.25

  "order:foodBaconExtra" -> ... -> display="Bacon", type="extra", weight=0.25

Non-food items (with both take/pour AND order) are set to type="other", weight=1.0, display=key.
Special: the listed beer glass BASES (guinessGlass, doombarGlass, etc.) are 'emptyGlass' type (NEVER included in potential orders).
Their Half/Full/Poured variants (e.g. madriGlassHalf, guinessGlassFull, madriGlassPoured) get type="beer", weight=1.0.
Special: items gotten via take:red*, take:white* or take:rose* (e.g. redFlagstonePoetryMerlot etc., excluding redbull; also their thimble *25/*50/*125 variants) are set to type="wine", weight=1.0.
Special: additional empty glasses like tallGlass, shortGlass, capriGlass, shotsGlass (from take:) are set to type="emptyGlass" (NEVER included).

This display_name will be used for customer speech/UI ("Bigstack Burger" not "foodBigstackBurger").
The type/weight will be used for weighting likelihood of customer asking for it.

TO UPDATE IN FUTURE: Tell me the new rules for stripping prefixes/suffixes, new types,
changes to WEIGHT_MAP, or new categories, and I'll update get_display_name() + get_food_type() + WEIGHT_MAP + the comments here.
"""

import json
from pathlib import Path
import sys
from collections import defaultdict
import re


def _get_project_root():
    """Find the project root containing NeuroMods/Bar/"""
    if getattr(sys, 'frozen', False):
        root = Path(sys._MEIPASS)
    else:
        root = Path(__file__).resolve().parent.parent.parent
    return root


def get_display_name(raw_name):
    """
    Compute human-friendly display name for food items ONLY.
    See module docstring for full documented logic.
    """
    s = raw_name

    # Step 2: remove one of the special prefixes (order already stripped)
    for pref in ["foodKidsBY", "foodKidsST", "foodKids", "food"]:
        if s.startswith(pref):
            s = s[len(pref):]
            break

    # Step 3: remove suffix
    for suf in ["Side", "Extra"]:
        if s.endswith(suf):
            s = s[:-len(suf)]
            break

    # Step 4: prettify camelCase -> spaced title words
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', s)
    s = s.strip()
    return s


def get_food_type(raw_name):
    """
    Determine type for food items.
    See module docstring for documented logic.
    """
    if raw_name.endswith("Side"):
        return "side"
    elif raw_name.endswith("Extra"):
        return "extra"
    else:
        # just a "food" (or foodKids*) prefix
        return "food"


# Weight mapping: how likely a customer is to ask for an item of this type.
# Used for weighted random selection when generating customer demands in practice mode.
# Non-food items are categorized as 'other'.
WEIGHT_MAP = {
    "food": 1.0,
    "side": 0.25,
    "extra": 0.25,
    "other": 1.0,
    "wine": 1.0,
    "beer": 1.0,
    "emptyGlass": 0.0,
}

# Beer glass BASES (e.g. madriGlass, guinessGlass). 
# These bases themselves are 'emptyGlass' type (empty containers, never in potential orders).
# Their Half and Full variants (e.g. madriGlassHalf, guinessGlassFull) get type 'beer'.
beer_glass_bases = {
    "guinessGlass", "doombarGlass", "caffreysGlass", "alpacalypseGlass",
    "madriGlass", "morettiGlass", "carlingGlass", "cruzcampoGlass", "coorsGlass"
}

# Additional empty glass items (from take:). These are also 'emptyGlass' and never included.
empty_glass_keys = beer_glass_bases | {
    "tallGlass", "shortGlass", "capriGlass", "shotsGlass"
}


def main():
    root = _get_project_root()
    buttons_file = root / "NeuroMods" / "Bar" / "till_buttons.json"
    bar_dir = root / "NeuroMods" / "Bar"
    out_nm = bar_dir / "potentialOrders.nm"

    if not buttons_file.exists():
        print(f"ERROR: Could not find {buttons_file}")
        sys.exit(1)

    with open(buttons_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Collect gettable (take: or pour:) and orderable items using exact raw names after the prefix.
    # No normalization — names must match exactly as the user defined them in the buttons.
    gettable = set()
    orderable = set()

    for view_name, buttons in data.items():
        if not isinstance(buttons, list):
            continue
        for btn in buttons:
            if not isinstance(btn, dict):
                continue
            action = str(btn.get("action", "")).strip()
            if not action or ":" not in action:
                continue

            prefix, _, name = action.partition(":")
            name = name.strip()
            if not name:
                continue

            p = prefix.lower()
            if p == "take" or p == "pour":
                gettable.add(name)
            elif p == "order":
                orderable.add(name)

    # Build potential orders:
    # - For normal items: must have both take:/pour: (acquire) AND order:
    # - For food items (order:food*): only need the order: button.
    # - For beer glass variants (e.g. madriGlassFull): order: for the variant is sufficient (acquired by pouring base).
    # - For thimble wine variants (e.g. redFoo25): order: for suffixed is sufficient (take plain wine + thimble:).
    #   (Food is sent to the kitchen, not acquired/made at the bar.)
    raw_potential = []
    for name in orderable:
        if name.lower().startswith("food"):
            raw_potential.append(name)
        elif name in gettable:
            raw_potential.append(name)
        elif any(name.startswith(base) and any(name.endswith(s) for s in ("Half", "Full", "Poured")) for base in beer_glass_bases):
            raw_potential.append(name)
        else:
            # thimble wine variants (e.g. redFlagstonePoetryMerlot25, or *125/*250): order: for suffixed is enough
            # (acquired via take:baseWine + thimble:NN in hand)
            stripped = name
            while stripped and stripped[-1].isdigit():
                stripped = stripped[:-1]
            if stripped != name and stripped and stripped.lower().startswith(("red", "white", "rose")) and not stripped.lower().startswith("redbull"):
                raw_potential.append(name)

    raw_potential = sorted(raw_potential)

    # Now enhance with display_name, type and weight.
    # - Food items: use the food display/type logic.
    # - Beer poured variants (order:xxxFull etc): included like food; type set to beer.
    # - Thimble wine variants (order:redXXX25 etc): included like food; will get type wine.
    # - All other (non-food) items that have take:/pour: + order: : type="other"
    potential_entries = []
    for key in raw_potential:
        if key.lower().startswith("food"):
            display = get_display_name(key)
            typ = get_food_type(key)
        else:
            display = key
            typ = "other"
        # Special case for wines: items gotten via take:red*, take:white* or take:rose*
        # (excluding redbull which is not wine). Also covers thimble variants like redXXX25
        if typ == "other" and key.lower().startswith(("red", "white", "rose")) and not key.lower().startswith("redbull"):
            typ = "wine"
        # Beer bases are emptyGlass, but their Half/Full/Poured variants are 'beer'
        if key in empty_glass_keys:
            typ = "emptyGlass"
            # Do not append to potential_entries
            continue
        if typ == "other" and any(key.startswith(base) and any(key.endswith(s) for s in ("Half", "Full", "Poured")) for base in beer_glass_bases):
            typ = "beer"
        weight = WEIGHT_MAP.get(typ, 1.0)
        potential_entries.append({
            "key": key,
            "display_name": display,
            "type": typ,
            "weight": weight
        })

    print(f"Found {len(potential_entries)} potential orders:")
    print("  (food* items only require order: button; others require take:/pour: + order:)")
    print("  (beer BASES like guinessGlass get 'emptyGlass' and are excluded; Half/Full/Poured get 'beer'; thimble wine *25/*50/*125 get 'wine'; other emptyGlasses excluded)")
    for e in potential_entries:
        print(f"  {e['key']} -> '{e['display_name']}' (type: {e['type']}, weight: {e['weight']})")

    # Write potentialOrders.nm with columns: key|display_name|type|weight
    # (one item per line, | separated)
    with open(out_nm, "w", encoding="utf-8") as f:
        f.write("# potentialOrders.nm\n")
        f.write("# Generated by src/bar/genOrders.py (python -m src.bar.genOrders)\n")
        f.write("# Potential orders for customer demands (practice mode) and .nm compilation.\n")
        f.write("# Columns: key|display_name|type|weight\n")
        f.write("# Rules (see top of this script for full documented logic):\n")
        f.write("#   - Non-food items: must have BOTH take:/pour: (to acquire) AND order: (to send) -> type=other, weight=1.0\n")
        f.write("#     (beer variants like madriGlassFull and thimble wines like redXXX25 get included on order: alone, like food*)\n")
        f.write("#   - Wine items (take:red* / white* / rose*): type=wine, weight=1.0\n")
        f.write("#   - Beer glass BASES (guinessGlass etc. from take:): type=emptyGlass (NEVER in potential orders)\n")
        f.write("#   - Beer Half/Full/Poured variants (madriGlassFull etc.): type=beer, weight=1.0\n")
        f.write("#   - Thimble wine variants (e.g. redFlagstonePoetryMerlot25 from order:): type=wine (included on order: alone)\n")
        f.write("#   - Empty glass containers (tallGlass, shortGlass, capriGlass, shotsGlass from take:): type=emptyGlass (NEVER included in potential orders)\n")
        f.write("#   - Food items (order:food*): only require order: button (food is sent to kitchen,\n")
        f.write("#     you don't 'take' or 'pour' it at the bar)\n")
        f.write("#   - display_name and type computed only for food items (see docstring)\n")
        f.write("#   - weight = how likely a customer is to ask for it (used for weighted random in demand gen)\n")
        f.write("# Used for practice-mode customer demand generation and POSSIBLE_DEMANDS.\n\n")
        f.write("# key|display_name|type|weight\n")
        for e in potential_entries:
            f.write(f"{e['key']}|{e['display_name']}|{e['type']}|{e['weight']}\n")

    print(f"\nWrote {out_nm}")

    # Also emit a ready-to-paste Python constant (for direct use or copy-paste into game.py)
    print("\n# Suggested Python list (copy into game.py if you want a static fallback):")
    print("# (food*, beer variants *Full/*Poured, and thimble wine variants *25/*50/*125 included via order: alone)")
    print("# Structured as list of dicts with key, display_name, type, weight")
    print("POSSIBLE_DEMANDS = [")
    for e in potential_entries:
        print(f"    {e},")
    print("]")


if __name__ == "__main__":
    main()
