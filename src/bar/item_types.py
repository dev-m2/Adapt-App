"""Shared item type classification for the bar trainer (game + genOrders)."""

from __future__ import annotations

import re

# Thimble pour sizes (ml). Longest suffixes are stripped first.
THIMBLE_SIZES: tuple[int, ...] = (250, 125, 50, 25)

SPIRIT_PREFIXES: tuple[str, ...] = (
    "vodka",
    "rum",
    "gin",
    "whiskey",
    "tequila",
    "liqueur",
    "courvoisier",
    "vermouth",
    "aperitif",
    "cognac",
    "brandy",
)

BEER_GLASS_BASES: frozenset[str] = frozenset({
    "guinessGlass", "doombarGlass", "caffreysGlass", "alpacalypseGlass",
    "madriGlass", "morettiGlass", "carlingGlass", "cruzcampoGlass", "coorsGlass",
})

EMPTY_GLASS_KEYS: frozenset[str] = BEER_GLASS_BASES | frozenset({
    "tallGlass", "shortGlass", "capriGlass", "shotsGlass",
})

SHOT_GLASS_KEYS: frozenset[str] = frozenset({"shotsGlass", "shotGlass"})

KIDS_PREFIXES: tuple[str, ...] = ("fruitshoot", "pip")

SOFT_PREFIXES: tuple[str, ...] = (
    "j20",
    "appletiser",
    "schweppes",
    "fevertree",
    "maybeschweppes",
    "sodaschweppes",
)

BOTTLE_BEER_MARKERS: frozenset[str] = frozenset({
    "peroniBottle", "heinekenBottle", "solBottle",
})

OPENED_SUFFIX = "Opened"

_CAN_RE = re.compile(r"(?:^|[a-z])Can(?:[A-Z]|$)")


def strip_thimble_suffix(key: str) -> tuple[str, int | None]:
    """Return (base_key, thimble_ml_or_none) stripping a trailing pour size."""
    s = str(key).strip()
    if not s:
        return s, None
    lower = s.lower()
    for size in THIMBLE_SIZES:
        suffix = str(size)
        if lower.endswith(suffix) and len(s) > len(suffix):
            return s[: -len(suffix)], size
    return s, None


def _has_can_segment(key: str) -> bool:
    return bool(key.endswith("Can") or _CAN_RE.search(key))


def _is_wine_key(key: str) -> bool:
    lower = key.lower()
    if lower.startswith("redbull"):
        return False
    return lower.startswith(("red", "white", "rose", "prosecco"))


def is_spirit_key(key: str) -> bool:
    """True for pourable spirit bottles (vodka*, rum*, gin*, etc.), not Single/Double serves."""
    if not key:
        return False
    base = key
    if base.endswith("Single"):
        base = base[: -len("Single")]
    elif base.endswith("Double"):
        base = base[: -len("Double")]
    lower = base.lower()
    return any(lower.startswith(p) for p in SPIRIT_PREFIXES)


def spirit_shot_single(spirit_base: str) -> str:
    return spirit_base + "Single"


def spirit_shot_double(spirit_base: str) -> str:
    return spirit_base + "Double"


def try_spirit_shot_pour(hand_item: str | None, spirit_base: str) -> tuple[str | None, bool]:
    """Progress a spirit shot pour in hand (like pour: for beer glasses).

    shotGlass + take:spirit → spiritSingle
    spiritSingle + same take:spirit → spiritDouble
    spiritDouble + same take:spirit → unchanged (handled, no further pour)

    Returns (new_hand_item, handled). handled=False → use normal take: overwrite.
    """
    if not spirit_base or not is_spirit_key(spirit_base):
        return None, False

    single = spirit_shot_single(spirit_base)
    double = spirit_shot_double(spirit_base)

    if hand_item in SHOT_GLASS_KEYS:
        return single, True
    if hand_item == single:
        return double, True
    if hand_item == double:
        return double, True
    return None, False


def classify_item_type(key: str) -> str:
    """Classify an item key for demand weighting and thimble eligibility.

    Returns one of:
      food, side, extra, wine, spirit, beer, emptyGlass,
      soft, can, bottleBeer, barFood, kids, other
    """
    if not key:
        return "other"

    base, _ = strip_thimble_suffix(key)
    lower = base.lower()

    if lower.startswith("food"):
        if base.endswith("Side"):
            return "side"
        if base.endswith("Extra"):
            return "extra"
        return "food"

    if base in EMPTY_GLASS_KEYS:
        return "emptyGlass"

    if any(lower.startswith(p) for p in KIDS_PREFIXES):
        return "kids"

    if lower.startswith("chips"):
        return "barFood"

    if _has_can_segment(base):
        return "can"

    if base in BOTTLE_BEER_MARKERS or (
        base.endswith("Bottle")
        and not _is_wine_key(base)
        and not is_spirit_key(base)
    ):
        return "bottleBeer"

    if any(lower.startswith(p) for p in SOFT_PREFIXES):
        return "soft"

    if any(base.startswith(b) and any(base.endswith(s) for s in ("Half", "Full", "Poured"))
            for b in BEER_GLASS_BASES):
        return "beer"

    if _is_wine_key(base):
        return "wine"

    if is_spirit_key(base):
        return "spirit"

    return "other"


def strip_opened_suffix(key: str) -> str:
    if key.endswith(OPENED_SUFFIX):
        return key[: -len(OPENED_SUFFIX)]
    return key


def is_opened_key(key: str) -> bool:
    return bool(key) and key.endswith(OPENED_SUFFIX)


def opened_key(key: str) -> str:
    return strip_opened_suffix(key) + OPENED_SUFFIX


def can_open_with_opener(key: str) -> bool:
    """True for RTD/soft bottles, beer bottles, and similar (not cans, wine, spirits)."""
    if not key or is_opened_key(key):
        return False
    typ = classify_item_type(key)
    if typ in ("soft", "bottleBeer"):
        return True
    if typ in ("can", "wine", "spirit", "beer", "emptyGlass", "food", "side", "extra", "barFood", "kids"):
        return False
    if typ == "other":
        if _has_can_segment(key):
            return False
        lower = key.lower()
        return lower.endswith("zero") or lower.endswith("bottle")
    return False


def try_open_bottle(hand_item: str | None) -> tuple[str | None, bool]:
    """opener: — convert a sealed bottle in hand to *Opened."""
    if not hand_item or not can_open_with_opener(hand_item):
        return None, False
    return opened_key(hand_item), True


def can_thimble(key: str | None) -> bool:
    """True if the item can be measured with thimble:25/50/125 (wines + spirits)."""
    if not key:
        return False
    base, _ = strip_thimble_suffix(str(key))
    return classify_item_type(base) in ("wine", "spirit")


def is_measured_pour(key: str | None) -> bool:
    """True if key is a thimble-measured wine or spirit (e.g. vodkaAbsolut25)."""
    if not key:
        return False
    base, amount = strip_thimble_suffix(str(key))
    return amount is not None and can_thimble(base)


def parse_measured_amount(key: str | None) -> tuple[str | None, int | None]:
    """Return (base_name, amount_ml) for a measured pour, or (None, None)."""
    if not key:
        return None, None
    base, amount = strip_thimble_suffix(str(key))
    if amount is None or not can_thimble(base):
        return None, None
    return base, amount


def combine_measured_pours(left: str | None, right: str | None) -> str | None:
    """Combine two thimble-measured wines/spirits of the same base into one key.

    Both hands must hold measured pours (e.g. redWineX25 + redWineX125 → redWineX150).
    Unmeasured base bottles (redWineX without a suffix) return None.
    """
    left_base, left_amt = parse_measured_amount(left)
    right_base, right_amt = parse_measured_amount(right)
    if (
        left_base is None
        or right_base is None
        or left_amt is None
        or right_amt is None
        or left_base != right_base
    ):
        return None
    return left_base + str(left_amt + right_amt)


# How likely practice-mode customers ask for each item category (weighted random).
DEMAND_WEIGHT_MAP: dict[str, float] = {
    "food": 1.0,
    "side": 0.25,
    "extra": 0.25,
    "wine": 1.0,
    "spirit": 1.0,
    "beer": 1.0,
    "soft": 1.0,
    "can": 1.0,
    "bottleBeer": 1.0,
    "barFood": 1.0,
    "kids": 1.0,
    "other": 1.0,
    "emptyGlass": 0.0,
}