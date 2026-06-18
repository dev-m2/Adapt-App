"""Human-readable names for customer demands and order UI."""

from __future__ import annotations

import re

from .item_types import (
    SPIRIT_PREFIXES,
    classify_item_type,
    is_spirit_key,
    strip_opened_suffix,
    strip_thimble_suffix,
)

FOOD_PREFIXES: tuple[str, ...] = ("foodKidsBY", "foodKidsST", "foodKids", "food")
FOOD_SUFFIXES: tuple[str, ...] = ("Side", "Extra")

WINE_COLOR_PREFIXES: tuple[str, ...] = ("red", "white", "rose")

# Words that indicate a plural item (no leading article).
_PLURAL_WORDS: frozenset[str] = frozenset({
    "bites", "pancakes", "wings", "chips", "mushrooms", "sticks", "nuggets",
    "crisps", "nachos", "tacos", "eggs", "beans", "peas", "sprouts", "mash",
    "nibbles",
})

# Optional overrides after prettify (key = lowercased compact form)
_DISPLAY_FIXES: dict[str, str] = {
    "ned sauvignon blanc": "Ned Sauvignon Blanc",
    "jack rabbit pinot grigio": "Jack Rabbit Pinot Grigio",
    "jam shed chardonnay": "Jam Shed Chardonnay",
    "andrew peace silhouette chardonnay": "Andrew Peace Silhouette Chardonnay",
    "flagstone poetry merlot": "Flagstone Poetry Merlot",
    "campo viejo rioja tempranillo": "Campo Viejo Rioja Tempranillo",
    "vino pomona pinot grigio": "Vino Pomona Pinot Grigio Rosé",
    "vina arroba tempranillo": "Viña Arroba Tempranillo",
    "guiness": "Guinness",
    "doombar": "Doom Bar",
    "madri": "Madri",
    "jagermeister": "Jägermeister",
    "jack daniel's": "Jack Daniel's",
    "jj london dry": "JJ London Dry",
    "jj whitley pink": "JJ Whitley Pink",
    "moretti": "Moretti",
    "carling": "Carling",
    "coors": "Coors",
    "cruzcampo": "Cruzcampo",
    "strongbow": "Strongbow",
    "lamma": "Lamma",
    "caffreys": "Caffreys",
    "stella": "Stella",
    "morreti": "Moretti",
}

_BEER_MEASURE_LABELS: dict[str, str] = {
    "Full": "Pint",
    "Half": "Half",
    "Poured": "Pint",  # legacy order keys → same customer wording as Full
}


def _prettify_camel(text: str) -> str:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    s = re.sub(r"\s*&\s*", " & ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _apply_display_fixes(name: str) -> str:
    key = name.lower()
    if key in _DISPLAY_FIXES:
        return _DISPLAY_FIXES[key]
    return name


def _strip_wine_color_prefix(key: str) -> str:
    lower = key.lower()
    if lower.startswith("redbull"):
        return key
    for prefix in WINE_COLOR_PREFIXES:
        if lower.startswith(prefix):
            return key[len(prefix):]
    return key


def _strip_spirit_category_prefix(key: str) -> str:
    """Remove leading spirit category (gin, vodka, liqueur, …); keep brand name."""
    lower = key.lower()
    for prefix in SPIRIT_PREFIXES:
        if lower.startswith(prefix):
            return key[len(prefix):]
    return key


def _insert_food_leading_modifier(leading: list[str], modifier: str) -> None:
    """Place Vegan (etc.) after Kids / Daytime labels, before the dish name."""
    insert_at = 0
    for i, label in enumerate(leading):
        if label in ("Kids", "Daytime"):
            insert_at = i + 1
    leading.insert(insert_at, modifier)


def _food_core_name(raw_name: str) -> str:
    """Build food display name with Kids / Daytime / Vegan leading labels."""
    s = raw_name
    leading: list[str] = []

    for pref in FOOD_PREFIXES:
        if s.startswith(pref):
            if pref.startswith("foodKids"):
                leading.append("Kids")
            s = s[len(pref):]
            break

    for suf in FOOD_SUFFIXES:
        if s.endswith(suf):
            s = s[:-len(suf)]
            break

    if s.endswith("Kids"):
        s = s[: -len("Kids")]
        if "Kids" not in leading:
            leading.append("Kids")

    if s.endswith("Daytime"):
        s = s[: -len("Daytime")]
        leading.append("Daytime")

    if s.endswith("Vegan"):
        s = s[: -len("Vegan")]
        _insert_food_leading_modifier(leading, "Vegan")
    elif s.startswith("Vegan") and len(s) > 5:
        s = s[5:]
        _insert_food_leading_modifier(leading, "Vegan")

    name = _apply_display_fixes(_prettify_camel(s))
    if leading:
        return " ".join(leading + [name])
    return name


def _spirit_core_name(key: str) -> str:
    return _apply_display_fixes(_prettify_camel(_strip_spirit_category_prefix(key)))


def _word_lower(word: str) -> str:
    w = word.lower()
    if w.endswith("'s"):
        return w[:-2]
    return w


def _is_plural_name(name: str) -> bool:
    words = re.findall(r"[A-Za-z']+", name)
    for word in words:
        w = _word_lower(word)
        if w in _PLURAL_WORDS:
            return True
        if w.endswith("ies") and len(w) > 3:
            return True
    if words:
        last = _word_lower(words[-1])
        if last.endswith("s") and last not in ("ross", "as", "is", "bus", "gas", "plus"):
            if not last.endswith("ss"):
                return True
    return False


def _needs_article(name: str) -> bool:
    return not _is_plural_name(name)


def get_display_name(raw_name: str) -> str:
    """Compute a human-readable name for any demand key (BarGame.nm response field)."""
    if not raw_name:
        return raw_name

    raw_name = strip_opened_suffix(raw_name)
    lower = raw_name.lower()
    if lower.startswith("food"):
        return _food_core_name(raw_name)

    base, amount = strip_thimble_suffix(raw_name)
    if amount is not None and classify_item_type(base) in ("wine", "spirit"):
        if classify_item_type(base) == "spirit":
            core = _spirit_core_name(base)
        else:
            core = _apply_display_fixes(_prettify_camel(_strip_wine_color_prefix(base)))
        return f"{core} {amount}ml"

    if raw_name.endswith("Double"):
        spirit_base = raw_name[: -len("Double")]
        if is_spirit_key(spirit_base):
            return f"{_spirit_core_name(spirit_base)} Double"

    if raw_name.endswith("Single"):
        spirit_base = raw_name[: -len("Single")]
        if is_spirit_key(spirit_base):
            return f"{_spirit_core_name(spirit_base)} Single"

    typ = classify_item_type(raw_name)
    if typ == "wine":
        return _apply_display_fixes(_prettify_camel(_strip_wine_color_prefix(raw_name)))
    if typ == "spirit":
        return _spirit_core_name(raw_name)
    if typ == "barFood" and lower.startswith("chips"):
        return _apply_display_fixes(_prettify_camel(raw_name[len("chips"):]))
    if typ == "beer" and raw_name.endswith(("Full", "Half", "Poured")):
        glass = raw_name
        suffix = ""
        for suf in ("Poured", "Full", "Half"):  # Poured before Full (longer match first)
            if glass.endswith(suf):
                glass = glass[: -len(suf)]
                suffix = suf
                break
        brand = _apply_display_fixes(_prettify_camel(glass.replace("Glass", "")))
        measure = _BEER_MEASURE_LABELS.get(suffix, suffix)
        if suffix == "Half":
            return f"Half {brand}"
        return f"{brand} {measure}"

    return _apply_display_fixes(_prettify_camel(raw_name.replace("_", "")))


def _food_modifier_type(raw_name: str) -> str | None:
    if not raw_name.lower().startswith("food"):
        return None
    if raw_name.endswith("Extra"):
        return "extra"
    if raw_name.endswith("Side"):
        return "side"
    return None


def _with_article(name: str) -> str:
    if not _needs_article(name):
        return name
    if name and name[0].lower() in "aeiou":
        return f"an {name}"
    return f"a {name}"


def _strip_leading_article(text: str) -> str:
    """Remove a leading a/an from a customer demand line."""
    lower = text.lower()
    if lower.startswith("an "):
        return text[3:]
    if lower.startswith("a "):
        return text[2:]
    return text


def format_counter_item(
    key: str,
    *,
    lookup: dict | None = None,
) -> str:
    """Short UI label for placed/sent boxes: customer wording without a/an."""
    meta = (lookup or {}).get(key, {})
    if meta.get("Display"):
        return _strip_leading_article(meta["Display"])
    return get_display_name(key)


def format_customer_demand(
    key: str,
    *,
    item_type: str | None = None,
    lookup: dict | None = None,
) -> str:
    """Format a demand key for customer speech / UI (with article or side/extra prefix)."""
    meta = (lookup or {}).get(key, {})
    if meta.get("Display"):
        return meta["Display"]
    base_key = strip_opened_suffix(key)
    name = get_display_name(base_key)
    typ = item_type or meta.get("type") or classify_item_type(base_key)

    food_mod = _food_modifier_type(key)
    if food_mod == "extra" or typ == "extra":
        return f"extra {name}"
    if food_mod == "side" or typ == "side":
        return f"side {name}"

    return _with_article(name)