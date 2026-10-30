"""
Ground Item Hider: a client-side loot filter for Borderlands 4.

Instead of teleporting or deleting loot, this only hides it. The pickup stays exactly where it
dropped, so turning the filter off brings it straight back.

An item is hidden if its rarity, manufacturer or type is selected. Items we can't recognize always
stay visible.

In highlight mode nothing is hidden. The selected items instead get a much stronger loot beam, and a
marker on a small radar. The game's own radar and compass are fed by native code we can't reach, so
this radar is our own widget.

Reading rarity from the loot beam is adapted from BL4 Loot Filter by Lango (GPL-3.0), which credits
SlippyCheeze for the original logic. https://github.com/jlangowells/bl4_loot_filter
The beam colour palettes and body paths were cross-checked with Loot Magnet by max0n4ik.
https://github.com/max0n4ik/LootMagnet

Where a pickup keeps its serial, and the serial format, come from bl4-fix by flameaway (GPL-3.0).
https://github.com/flameaway/bl4-fix
The table of firmware parts comes from bl4 by monokrome (BSD-2-Clause).
https://github.com/monokrome/bl4
"""

from __future__ import annotations

import ctypes
import math
import re
import struct
import sys
import time
from dataclasses import dataclass
from typing import Any

from mods_base import (
    BaseOption,
    BoolOption,
    NestedOption,
    SliderOption,
    SpinnerOption,
    build_mod,
    get_pc,
    hook,
    keybind,
)
from unrealsdk import construct_object, find_all, find_class, find_object, make_struct
from unrealsdk.hooks import Type
from unrealsdk.logging import info, warning
from unrealsdk.unreal import BoundFunction, UObject, WeakPointer, WrappedStruct

COMMON = "Common"
UNCOMMON = "Uncommon"
RARE = "Rare"
EPIC = "Epic"
LEGENDARY = "Legendary"
PEARLESCENT = "Pearlescent"
RARITY_ORDER = (COMMON, UNCOMMON, RARE, EPIC, LEGENDARY, PEARLESCENT)

AMMO = "Ammo"
HEALTH = "Health"
MONEY = "Money"
ERIDIUM = "Eridium"
SHIELD_BOOSTER = "Shield Boosters"
MISSION = "Mission"

PISTOL = "Pistols"
SMG = "SMGs"
ASSAULT_RIFLE = "Assault Rifles"
SHOTGUN = "Shotguns"
SNIPER = "Sniper Rifles"
HEAVY_WEAPON = "Heavy Weapons"
SHIELD = "Shields"
GRENADE = "Grenades"
REPAIR_KIT = "Repair Kits"
ENHANCEMENT = "Enhancements"
CLASS_MOD = "Class Mods"

GEAR_BODY_PATHS = {
    "/Gear/Weapons/Pistols/": PISTOL,
    "/Gear/Weapons/SMG/": SMG,
    "/Gear/Weapons/AssaultRifles/": ASSAULT_RIFLE,
    "/Gear/Weapons/Shotguns/": SHOTGUN,
    "/Gear/Weapons/Sniper/": SNIPER,
    "/Gear/Gadgets/HeavyWeapons/": HEAVY_WEAPON,
    "/Gear/Shields/": SHIELD,
    "/Gear/GrenadeGadgets/": GRENADE,
    "/Gear/RepairKits/": REPAIR_KIT,
    "/Gear/Enhancements/": ENHANCEMENT,
    "/Gear/ClassMods/": CLASS_MOD,
}

MANUFACTURER_CODES = {
    "ATLAS": "Atlas",
    "COV": "COV",
    "DAD": "Daedalus",
    "HYP": "Hyperion",
    "JAK": "Jakobs",
    "MAL": "Maliwan",
    "ORD": "Order",
    "BOR": "Ripper",
    "TED": "Tediore",
    "TOR": "Torgue",
    "VLA": "Vladof",
}

# How each character is named in class mods' body paths, lowercase without underscores.
CHARACTER_CODES = {
    "paladin": "Amon",
    "robodealer": "C4SH",
    "gravitar": "Harlowe",
    "corpohacker": "Loveless",
    "loveless": "Loveless",
    "exosoldier": "Rafa",
    "darksiren": "Vex",
}
CHARACTERS = tuple(sorted(set(CHARACTER_CODES.values())))

# Which part of each gear category is which firmware. In a serial, these look like {246:12}.
FIRMWARE_PARTS = {
    234: {74: "risky_boots", 75: "god_killer", 76: "reel_big_fist", 77: "lifeblood", 78: "airstrike", 79: "high_caliber", 80: "gadget_ahoy", 81: "baker", 82: "oscar_mike", 83: "rubberband_man", 84: "deadeye", 85: "action_fist", 86: "goojfc", 87: "atlas_ex", 88: "atlas_infinum", 89: "trickshot", 90: "jacked", 91: "get_throwin", 92: "heating_up", 93: "bullets_to_spare", 94: "daeddy_o", 103: "skillcraft", 104: "active_fire", 106: "bruiser"},
    243: {1: "god_killer", 2: "reel_big_fist", 3: "lifeblood", 4: "airstrike", 5: "high_caliber", 6: "gadget_ahoy", 7: "baker", 8: "oscar_mike", 9: "rubberband_man", 10: "deadeye", 11: "action_fist", 12: "goojfc", 13: "atlas_ex", 14: "atlas_infinum", 15: "trickshot", 16: "jacked", 17: "get_throwin", 18: "heating_up", 19: "bullets_to_spare", 20: "daeddy_o", 112: "risky_boots", 113: "skillcraft", 114: "active_fire", 120: "bruiser"},
    244: {1: "god_killer", 2: "reel_big_fist", 3: "lifeblood", 4: "airstrike", 5: "high_caliber", 6: "gadget_ahoy", 7: "baker", 8: "oscar_mike", 9: "rubberband_man", 10: "deadeye", 11: "action_fist", 12: "goojfc", 13: "atlas_ex", 14: "atlas_infinum", 15: "trickshot", 16: "jacked", 17: "get_throwin", 18: "heating_up", 19: "bullets_to_spare", 20: "daeddy_o", 26: "risky_boots", 27: "skillcraft", 28: "active_fire", 29: "bruiser"},
    245: {1: "god_killer", 2: "reel_big_fist", 3: "lifeblood", 4: "airstrike", 5: "high_caliber", 6: "gadget_ahoy", 7: "baker", 8: "oscar_mike", 9: "rubberband_man", 10: "deadeye", 11: "action_fist", 12: "goojfc", 13: "atlas_ex", 14: "atlas_infinum", 15: "trickshot", 16: "jacked", 17: "get_throwin", 18: "heating_up", 19: "bullets_to_spare", 20: "daeddy_o", 87: "risky_boots", 88: "skillcraft", 89: "active_fire", 90: "bruiser"},
    246: {1: "god_killer", 2: "reel_big_fist", 3: "lifeblood", 4: "airstrike", 5: "high_caliber", 6: "gadget_ahoy", 7: "baker", 8: "oscar_mike", 9: "rubberband_man", 10: "deadeye", 11: "action_fist", 12: "goojfc", 13: "atlas_ex", 14: "atlas_infinum", 15: "trickshot", 16: "jacked", 17: "get_throwin", 18: "heating_up", 19: "bullets_to_spare", 20: "daeddy_o", 64: "risky_boots", 65: "skillcraft", 66: "active_fire", 67: "bruiser"},
    247: {1: "god_killer", 2: "reel_big_fist", 3: "lifeblood", 4: "airstrike", 5: "high_caliber", 6: "gadget_ahoy", 7: "baker", 8: "oscar_mike", 9: "rubberband_man", 10: "deadeye", 11: "action_fist", 12: "goojfc", 13: "atlas_ex", 14: "atlas_infinum", 15: "trickshot", 16: "jacked", 17: "get_throwin", 18: "heating_up", 19: "bullets_to_spare", 20: "daeddy_o", 103: "risky_boots", 248: "skillcraft", 249: "active_fire", 250: "bruiser"},
}
FIRMWARE_NAMES = {
    "action_fist": "Action Fist",
    "active_fire": "Active Fire",
    "airstrike": "Airstrike",
    "atlas_ex": "Atlas E.X.",
    "atlas_infinum": "Atlas Infinum",
    "baker": "Baker",
    "bruiser": "Bruiser",
    "bullets_to_spare": "Bullets To Spare",
    "daeddy_o": "Daed-dy O'",
    "deadeye": "Deadeye",
    "gadget_ahoy": "Gadget Ahoy",
    "get_throwin": "Get Throwin'",
    "god_killer": "God Killer",
    "goojfc": "Goojfc",
    "heating_up": "Heating Up",
    "high_caliber": "High Caliber",
    "jacked": "Jacked",
    "lifeblood": "Lifeblood",
    "oscar_mike": "Oscar Mike",
    "reel_big_fist": "Reel Big Fist",
    "risky_boots": "Risky Boots",
    "rubberband_man": "Rubberband Man",
    "skillcraft": "Skillcraft",
    "trickshot": "Trickshot",
}

# Where a pickup keeps its serial. These can move with a game update, in which case what's there
# doesn't look like a serial, and the firmware just stays unknown.
PICKUP_IDENTITY = 0x3F0
IDENTITY_SERIAL_POINTER = 0xA0
IDENTITY_SERIAL_LENGTH = 0xB0
SERIAL_MAX_LENGTH = 4096
SERIAL_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!#$%&()*+-;<=>?@^_`{/}~"
SERIAL_DIGITS = {char: value for value, char in enumerate(SERIAL_ALPHABET)}
SERIAL_PAD = 84
SERIAL_MAGIC = "0010000"

# The value of the beam's User.Color parameter. Both palettes have been seen in the live game.
BEAM_COLORS = (
    ((0.514918, 0.491021, 0.623961, 1.0), COMMON),
    ((0.095307, 0.558341, 0.111932, 1.0), UNCOMMON),
    ((0.018500, 0.337164, 0.590619, 1.0), RARE),
    ((0.479320, 0.056128, 0.658375, 1.0), EPIC),
    ((1.0, 0.229151, 0.0, 1.0), LEGENDARY),
    ((0.309469, 1.0, 0.644480, 1.0), PEARLESCENT),
    ((0.287441, 0.278894, 0.391573, 1.0), COMMON),
    ((0.010330, 0.250158, 0.025187, 1.0), UNCOMMON),
    ((0.016807, 0.119538, 0.434154, 1.0), RARE),
    ((0.254152, 0.010330, 0.450786, 1.0), EPIC),
    ((0.435, 0.435, 0.435, 1.0), AMMO),
    ((0.5, 0.0, 1.0, 1.0), ERIDIUM),
    ((1.0, 0.0, 0.0, 1.0), HEALTH),
    ((0.0, 1.0, 1.0, 1.0), MISSION),
    ((1.0, 1.0, 0.0, 1.0), MONEY),
)
BEAM_COLOR_TOLERANCE = 0.00002

# Some pickups have no BodyData or beam, these are matched against the material's name instead.
PICKUP_MATERIAL_NAMES = {
    "Ammo": AMMO,
    "ammo": AMMO,
    "AMMO": AMMO,
    "Health": HEALTH,
    "Money": MONEY,
    "Eridium": ERIDIUM,
    "ShieldBooster": SHIELD_BOOSTER,
    "ShieldBoosters": SHIELD_BOOSTER,
}

NIAGARA_FALSE = bytes((0x00, 0x00, 0x00, 0x00))

# The on screen warning, plain UMG built in code like the notices in bl4-fix by flameaway.
# https://github.com/flameaway/bl4-fix
BANNER_TEXT = "FILTR AKTYWNY"
BANNER_NAME = "GroundItemHider_Banner"
BANNER_Z_ORDER = 20
BANNER_MARGIN = 24.0
BANNER_FONT_SIZE = 16
BANNER_FONT = "/Game/Fonts/Industry.Industry"
BANNER_TYPEFACE = "Bold"
HIT_TEST_INVISIBLE = 3
# UMG colours are linear
BANNER_BACKGROUND = (0.0012, 0.0052, 0.0098, 0.88)
BANNER_COLOR = (1.0, 0.45, 0.02, 1.0)
BANNER_COLOR_HIGHLIGHT = (1.0, 0.0, 0.45, 1.0)
BANNER_TEXT_COLOR = (0.776, 0.693, 0.617, 1.0)
BANNER_TEXT_HIGHLIGHT = "FILTR AKTYWNY: PODSWIETLANIE"
RESTART_NOTICE_TEXT = "Uruchom grę ponownie, aby włączyć menu modów (F7)"
RESTART_NOTICE_FONT_SIZE = 13
RESTART_NOTICE_TOP = 62.0  # Leaves room for the banner above it

MODE_HIDE = "Ukrywanie"
MODE_HIGHLIGHT = "Podświetlanie"

# What's shown in the menus. Option identifiers stay in English, those are the settings file's keys.
RARITY_LABELS = {
    COMMON: "Pospolite",
    UNCOMMON: "Niepospolite",
    RARE: "Rzadkie",
    EPIC: "Epickie",
    LEGENDARY: "Legendarne",
    PEARLESCENT: "Perłowe",
}
GEAR_TYPE_LABELS = {
    PISTOL: "Pistolety",
    SMG: "Pistolety maszynowe",
    ASSAULT_RIFLE: "Karabiny szturmowe",
    SHOTGUN: "Strzelby",
    SNIPER: "Karabiny snajperskie",
    HEAVY_WEAPON: "Broń ciężka",
    SHIELD: "Tarcze",
    GRENADE: "Granaty",
    REPAIR_KIT: "Zestawy naprawcze",
    ENHANCEMENT: "Ulepszenia",
    CLASS_MOD: "Mody klasowe",
}
PICKUP_LABELS = {
    AMMO: "Amunicja",
    HEALTH: "Zdrowie",
    MONEY: "Pieniądze",
    ERIDIUM: "Eridium",
    SHIELD_BOOSTER: "Wzmocnienia tarczy",
}

# What the loot beam (NS_FX_Item_Loot_Beams) is told to do. The colour has no upper limit, anything
# above 1 is what makes it bloom. The legendary flag switches it to the game's big legendary beam.
BEAM_COLOR_PARAM = "User.Color"
BEAM_LEGENDARY_PARAM = "User.IsLegendary"
BEAM_FIRMWARE_PARAM = "User.HasFirmware"
BEAM_ANOINTED_PARAM = "User.HasAnointment"
BEAM_SHINY_PARAM = "User.IsShiny"
# How close the colour must be to what we wrote to still count as ours
BEAM_BOOST_TOLERANCE = 0.01

# Reading a pickup goes through the game a lot, so what doesn't change is remembered. A pickup which
# is already handled costs next to nothing. After a big fight the new ones are read a few at a time,
# within a time limit, so one scan never holds up a frame for long.
MAX_READS_PER_SCAN = 10
SCAN_TIME_LIMIT = 0.0015
BACKLOG_INTERVAL = 0.03
INFO_MAX_AGE = 30.0  # Looks at each pickup again now and then, in case the game reused the actor
INCOMPLETE_RETRY = 0.5  # A fresh drop may not have its beam set up yet
BOOST_CHECK_INTERVAL = 2.0  # The game may change a boosted beam back
SKIPPED_ITEM_RETRY = 2.0  # For pickups the game has hidden itself, or which caused an error
VENDING_INTERVAL = 5.0
WIDGET_CHECK_INTERVAL = 1.0
# However long scans turn out to take here, they never take over 2% of the time
SCAN_TIME_SHARE = 50.0
SLOWEST_SCAN_INTERVAL = 2.0
SLOW_SCAN_MS = 8.0  # About half a frame at 60 fps
SLOW_SCAN_LOG_INTERVAL = 60.0

COLLAPSED = 1
DRAW_ROUNDED_BOX = 4
ROUND_HALF_HEIGHT = 1
RADAR_Z_ORDER = 19
RADAR_SIZE = 160.0
# The game has its own round radar in the top right, this one has to stay clear of it
RADAR_LEFT = "Lewy górny róg"
RADAR_RIGHT = "Prawa strona, pod radarem gry"
RADAR_TOP_LEFT = 24.0
RADAR_TOP_RIGHT = 270.0
RADAR_ARROW = (
    "/Game/uiresources/enemy_radar/assets/ui_art_asset/"
    "enemy_radar_circle_player_arrow.enemy_radar_circle_player_arrow"
)
RADAR_INTERVAL = 0.05
RADAR_MARKER_SIZE = 14.0
RADAR_MAX_MARKERS = 32
RADAR_BACKGROUND = (0.0012, 0.0052, 0.0098, 0.75)
RADAR_RING = (0.13, 0.62, 1.0, 1.0)
RADAR_INNER_RING = (0.13, 0.62, 1.0, 0.35)
RADAR_CLEAR = (0.0, 0.0, 0.0, 0.0)
RADAR_PLAYER = (1.0, 1.0, 1.0, 1.0)
RADAR_MARKER_DEFAULT = (1.0, 0.0, 0.45, 1.0)
RADAR_MARKER_OUTLINE = (0.0, 0.0, 0.0, 1.0)

rarity_options = {
    COMMON: BoolOption(COMMON, True, description="Hide white items."),
    UNCOMMON: BoolOption(UNCOMMON, True, description="Hide green items."),
    RARE: BoolOption(RARE, True, description="Hide blue items."),
    EPIC: BoolOption(EPIC, False, description="Hide purple items."),
    LEGENDARY: BoolOption(LEGENDARY, False, description="Hide orange items."),
    PEARLESCENT: BoolOption(PEARLESCENT, False, description="Hide pearlescent items."),
}

manufacturer_options = {
    name: BoolOption(name, False, description=f"Hide gear made by {name}.")
    for name in sorted(MANUFACTURER_CODES.values())
}

gear_type_options = {
    name: BoolOption(name, False, description=f"Hide all {name}.")
    for name in GEAR_BODY_PATHS.values()
}

character_options = {name: BoolOption(name, False) for name in CHARACTERS}

pickup_options = {
    name: BoolOption(name, False, description=f"Hide {name.lower()} pickups.")
    for name in (AMMO, HEALTH, MONEY, ERIDIUM, SHIELD_BOOSTER)
}

NO_PROTECTION = "Wyłączona"
protected_rarity = SpinnerOption(
    "Protect Rarity And Above",
    RARITY_LABELS[LEGENDARY],
    [NO_PROTECTION, RARITY_LABELS[EPIC], RARITY_LABELS[LEGENDARY], RARITY_LABELS[PEARLESCENT]],
    display_name="Chroń tę rzadkość i wyższe",
    description=(
        "Sprzęt tej rzadkości i lepszy ignoruje filtry firm i typów, więc ukrycie Jakobsa nie schowa"
        " legendarnego Jakobsa. Filtr rzadkości nadal działa."
    ),
)
keep_firmware = BoolOption(
    "Always Show Firmware",
    True,
    description="Never hide gear with firmware, whatever filters match it.",
)
keep_anointed = BoolOption(
    "Always Show Anointed",
    True,
    description="Never hide gear with an anointment, whatever filters match it.",
)
keep_shiny = BoolOption(
    "Always Show Shiny",
    True,
    description="Never hide shiny gear, whatever filters match it.",
)
filter_mode = SpinnerOption(
    "Filter Mode",
    MODE_HIDE,
    [MODE_HIDE, MODE_HIGHLIGHT],
    description=(
        "Hide: selected items disappear from the ground. Highlight: everything drops as normal, and"
        " the items selected under Highlight Filters get a strong beam and a radar marker."
    ),
)

highlight_rarity_options = {
    name: BoolOption(name, name in (LEGENDARY, PEARLESCENT), description=f"Highlight {name} items.")
    for name in RARITY_ORDER
}
highlight_manufacturer_options = {
    name: BoolOption(name, False, description=f"Highlight gear made by {name}.")
    for name in sorted(MANUFACTURER_CODES.values())
}
highlight_gear_type_options = {
    name: BoolOption(name, False, description=f"Highlight all {name}.")
    for name in GEAR_BODY_PATHS.values()
}
highlight_character_options = {name: BoolOption(name, False) for name in CHARACTERS}
firmware_options = {key: BoolOption(name, True) for key, name in sorted(FIRMWARE_NAMES.items())}
highlight_firmware_options = {key: BoolOption(name, True) for key, name in sorted(FIRMWARE_NAMES.items())}
highlight_pickup_options = {
    name: BoolOption(name, False, description=f"Highlight {name.lower()} pickups.")
    for name in (AMMO, HEALTH, MONEY, ERIDIUM, SHIELD_BOOSTER)
}
highlight_firmware = BoolOption(
    "Highlight Firmware",
    True,
    description="Highlight all gear with firmware.",
)
highlight_anointed = BoolOption(
    "Highlight Anointed",
    True,
    description="Highlight all gear with an anointment.",
)
highlight_shiny = BoolOption(
    "Highlight Shiny",
    True,
    description="Highlight all shiny gear.",
)
beam_intensity = SliderOption(
    identifier="Beam Brightness",
    value=30.0,
    min_value=1.0,
    max_value=100.0,
    step=1.0,
    is_integer=False,
    description="How many times brighter than normal to make the beam of a highlighted item.",
)
beam_size = SliderOption(
    identifier="Beam Size",
    value=2.0,
    min_value=1.0,
    max_value=5.0,
    step=0.5,
    is_integer=False,
    description="How many times bigger than normal to make the beam of a highlighted item.",
)
show_radar = BoolOption(
    "Show Radar",
    True,
    description="Show highlighted items on a small radar in the top right, which turns with you.",
)
radar_place = SpinnerOption("Radar Position", RADAR_LEFT, [RADAR_LEFT, RADAR_RIGHT])
radar_range = SliderOption(
    identifier="Radar Range",
    value=100.0,
    min_value=25.0,
    max_value=500.0,
    step=25.0,
    is_integer=False,
    description="Metres to the edge of the radar. Items further away stay on its edge.",
)

scan_interval = SliderOption(
    identifier="Scan Interval Seconds",
    value=0.25,
    min_value=0.1,
    max_value=2.0,
    step=0.05,
    is_integer=False,
    description="Seconds between looking for new loot. Raise this if you notice stutters.",
)

paused: bool = False
last_scan: float = 0.0
# Only ever unhide what we hid ourselves, the game hides some pickups for its own reasons.
hidden_by_us: set[int] = set()
reported_colors: set[tuple[float, ...]] = set()
banner_widget: WeakPointer = WeakPointer()
banner_owner: WeakPointer = WeakPointer()
banner_error_logged: bool = False
banner_text: str = ""
banner_label: UObject | None = None
banner_mode: str = ""
restart_notice: UObject | None = None
restart_notice_shown: bool = False


@dataclass
class BoostedBeam:
    """What a beam looked like before we boosted it, and what we changed it to."""

    color: tuple[float, ...]
    kind: str | None
    was_legendary: bool
    scale: tuple[float, float, float]
    boosted_color: tuple[float, ...]
    boosted_size: float


@dataclass
class ItemInfo:
    """What a pickup is, which doesn't change. Decisions are made from this every scan."""

    body: str
    material: str
    kind: str | None
    has_beam: bool
    firmware: bool
    firmware_name: str | None  # A key of FIRMWARE_NAMES, None if there's none or it's not known
    anointed: bool
    shiny: bool
    read_at: float


item_infos: dict[int, ItemInfo] = {}
known_classes: dict[str, UObject] = {}
vending_items: set[int] = set()
last_vending: float = -VENDING_INTERVAL
actor_search_failed: bool = False
scan_times_ms: list[float] = []
slowest_scan_ms: float = 0.0
last_slow_log: float = -SLOW_SCAN_LOG_INTERVAL
boosted_beams: dict[int, BoostedBeam] = {}
beam_error_logged: bool = False
highlighted_items: list[tuple[WeakPointer, str | None]] = []
highlight_pointers: dict[int, WeakPointer] = {}
radar_items: list[tuple[float, float, str | None]] = []
last_boost_check: float = 0.0
last_widget_check: float = -WIDGET_CHECK_INTERVAL
last_scan_seconds: float = 0.0
scan_backlog: bool = False
decided_with: dict[int, int] = {}
skip_until: dict[int, float] = {}
scan_error_logged: bool = False
last_state: tuple | None = None
state_revision: int = 0
last_radar: float = 0.0
radar_widget: WeakPointer = WeakPointer()
radar_owner: WeakPointer = WeakPointer()
radar_markers: list[UObject] = []
radar_markers_shown: list[bool] = []
radar_marker_positions: list[tuple[float, float] | None] = []
radar_marker_kinds: list[str | None] = []
radar_built_place: str = ""
radar_error_logged: bool = False


def classify_color(color: tuple[float, ...]) -> str | None:
    """Finds what a beam colour stands for. There's no nearest match, unknowns return None."""
    if not all(math.isfinite(value) for value in color):
        return None
    for expected, kind in BEAM_COLORS:
        if all(abs(a - b) <= BEAM_COLOR_TOLERANCE for a, b in zip(color, expected, strict=True)):
            return kind
    return None


def read_beam_values(beam: UObject) -> tuple[bytes, dict[str, int]]:
    """Reads a beam's parameters in one go. This is the slowest part of reading a pickup."""
    store = beam.OverrideParameters
    return bytes(store.ParameterData), {str(param.Name): param.Offset for param in store.SortedParameterOffsets}


def beam_color(values: tuple[bytes, dict[str, int]]) -> tuple[float, ...] | None:
    """Gets a beam's colour from its parameters."""
    data, offsets = values
    offset = offsets.get(BEAM_COLOR_PARAM, -1)
    # A parameter which isn't set has a negative offset
    if offset < 0 or offset + 16 > len(data):
        return None
    return struct.unpack_from("<4f", data, offset)


def beam_flag(values: tuple[bytes, dict[str, int]], name: str) -> bool:
    """Gets one of a beam's flags from its parameters."""
    data, offsets = values
    offset = offsets.get(name, -1)
    return 0 <= offset and offset + 4 <= len(data) and data[offset : offset + 4] != NIAGARA_FALSE


def read_beam_color(beam: UObject) -> tuple[float, ...] | None:
    """Reads the beam's current colour."""
    return beam_color(read_beam_values(beam))


def read_beam_flag(beam: UObject, name: str) -> bool:
    """Reads one of the beam's flags."""
    return beam_flag(read_beam_values(beam), name)


def colors_match(first: tuple[float, ...], second: tuple[float, ...]) -> bool:
    """Checks if two colours are the same, give or take float precision."""
    return all(abs(a - b) <= BEAM_BOOST_TOLERANCE for a, b in zip(first, second, strict=True))


def color_kind(color: tuple[float, ...] | None, key: int) -> str | None:
    """Gets what a beam's colour stands for, seeing through our own boost."""
    if color is None:
        return None

    boosted = boosted_beams.get(key)
    if boosted is not None:
        if colors_match(color, boosted.boosted_color):
            return boosted.kind
        # The game changed it back, or reused this actor for something else
        del boosted_beams[key]

    kind = classify_color(color)
    if kind is None and color not in reported_colors:
        reported_colors.add(color)
        warning(f"[Ground Item Hider] Unknown beam colour, ignoring the item: {color}")
    return kind


def get_beam_kind(beam: UObject, key: int) -> str | None:
    """Reads what a beam's colour stands for."""
    return color_kind(read_beam_color(beam), key)


def get_material_name(item: UObject) -> str:
    """Gets the name of the pickup's first material, or an empty string if it has none."""
    root = item.RootPrimitiveComponent
    if root.GetNumMaterials() == 0:
        return ""
    material = root.GetMaterial(0)
    return str(material.Name) if material else ""


def get_gear_type(body: str) -> str | None:
    """Gets the type of a piece of gear from its body's path."""
    for path, gear_type in GEAR_BODY_PATHS.items():
        if path in body:
            return gear_type
    return None


def get_manufacturer(body: str, material: str) -> str | None:
    """
    Gets the manufacturer of a piece of gear.

    Weapons, shields, grenades and heavy weapons have it in their body's path. Repair kits and
    enhancements only have it in their material, e.g. MID_M_JAK_.
    """
    for source in (body, material):
        for part in re.split(r"[/_.']", source):
            manufacturer = MANUFACTURER_CODES.get(part)
            if manufacturer is not None:
                return manufacturer
    return None


def get_character(body: str) -> str | None:
    """Gets which character a class mod is for, from its body's path."""
    path = body.lower().replace("_", "")
    for code, character in CHARACTER_CODES.items():
        if code in path:
            return character
    return None


def is_protected(rarity: str) -> bool:
    """Checks if a rarity is exempt from the manufacturer and item type filters."""
    if protected_rarity.value == NO_PROTECTION:
        return False
    protected = next(key for key, label in RARITY_LABELS.items() if label == protected_rarity.value)
    return RARITY_ORDER.index(rarity) >= RARITY_ORDER.index(protected)


def item_key(item: UObject) -> int:
    """Gets a cheap id for a pickup. Reading its name, let alone its full path, each time adds up."""
    return item._get_address()  # noqa: SLF001


def read_memory(address: int, size: int) -> bytes | None:
    """Reads memory such that a bad address fails, instead of crashing the game."""
    if not 0x10000 <= address < 0x7FFFFFFFFFFF or size <= 0:
        return None
    buffer = ctypes.create_string_buffer(size)
    done = ctypes.c_size_t()
    kernel32 = ctypes.windll.kernel32
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    if not kernel32.ReadProcessMemory(
        ctypes.c_void_p(kernel32.GetCurrentProcess()),
        ctypes.c_void_p(address),
        buffer,
        ctypes.c_size_t(size),
        ctypes.byref(done),
    ):
        return None
    return buffer.raw if done.value == size else None


def read_item_serial(item: UObject) -> str | None:
    """Reads a pickup's serial. There's no reflected way to get to it, it's only in native memory."""
    identity = item_key(item) + PICKUP_IDENTITY
    head = read_memory(identity + IDENTITY_SERIAL_POINTER, IDENTITY_SERIAL_LENGTH - IDENTITY_SERIAL_POINTER + 8)
    if head is None:
        return None
    pointer = int.from_bytes(head[:8], "little")
    length = int.from_bytes(head[IDENTITY_SERIAL_LENGTH - IDENTITY_SERIAL_POINTER :], "little")
    if not 2 < length <= SERIAL_MAX_LENGTH:
        return None
    text = read_memory(pointer, length)
    if text is None:
        return None
    serial = text.split(b"\0", 1)[0].decode("ascii", "replace")
    return serial if serial.startswith("@U") else None


class SerialBits:
    """Reads a serial's bit stream."""

    def __init__(self, serial: str) -> None:
        data = bytearray()
        digits = [SERIAL_DIGITS[char] for char in serial[2:] if char in SERIAL_DIGITS]
        for start in range(0, len(digits), 5):
            group = digits[start : start + 5]
            value = 0
            for digit in group + [SERIAL_PAD] * (5 - len(group)):
                value = value * 85 + digit
            value &= 0xFFFFFFFF
            data += value.to_bytes(4, "big")[: 4 if len(group) == 5 else len(group) - 1]
        # Each byte is mirrored, so this reads them backwards to get the same thing
        self.bits = "".join(f"{byte:08b}"[::-1] for byte in data)
        self.position = 0

    def take(self, count: int) -> str:
        end = self.position + count
        if end > len(self.bits):
            raise ValueError("serial ends early")
        chunk = self.bits[self.position : end]
        self.position = end
        return chunk

    def left(self) -> int:
        return len(self.bits) - self.position

    def number(self, count: int) -> int:
        return int(self.take(count)[::-1], 2) if count else 0

    def varint(self) -> int:
        value = shift = 0
        for _ in range(4):
            value |= self.number(4) << shift
            shift += 4
            if self.take(1) == "0":
                break
        return value

    def token(self) -> str | None:
        if self.left() < 2:
            return None
        head = self.take(2)
        if head in ("00", "01"):
            return head
        return head + self.take(1) if self.left() else None


def serial_firmware(serial: str) -> str | None:
    """Finds which firmware a serial has, as a key of FIRMWARE_NAMES. None if it has none we know."""
    reader = SerialBits(serial)
    if reader.take(7) != SERIAL_MAGIC:
        return None

    while (kind := reader.token()) is not None:
        if kind == "100":
            reader.varint()
        elif kind == "110":
            reader.number(reader.number(5))
        elif kind == "111":
            reader.take(7 * reader.varint())
        elif kind == "101":
            table = FIRMWARE_PARTS.get(reader.varint())
            values = []
            if reader.take(1) == "1":
                values.append(reader.varint())
                if reader.take(3) != "000":
                    return None
            else:
                flag = reader.take(2)
                if flag == "01":
                    if reader.token() != "01":
                        return None
                    while (item := reader.token()) != "00":
                        if item == "100":
                            values.append(reader.varint())
                        elif item == "110":
                            values.append(reader.number(reader.number(5)))
                        else:
                            return None
                elif flag != "10":
                    return None
            for value in values if table is not None else ():
                if value in table:
                    return table[value]
        elif kind not in ("00", "01"):
            return None
    return None


def read_item_firmware(item: UObject) -> str | None:
    """Works out which firmware a pickup has. Any problem just means it's not known."""
    try:
        serial = read_item_serial(item)
        return serial_firmware(serial) if serial else None
    except Exception:  # noqa: BLE001
        return None


def read_item_info(item: UObject, key: int) -> ItemInfo:
    """Does the slow reads for a pickup."""
    body = str(item.BodyData) if item.BodyData else ""
    material = get_material_name(item)
    beam = item.AttractEffectComponent
    values = read_beam_values(beam) if beam else (b"", {})
    kind = color_kind(beam_color(values), key)
    if kind is None and "/Gear/" not in body:
        for part in material.split("_"):
            kind = PICKUP_MATERIAL_NAMES.get(part)
            if kind is not None:
                break
    firmware = beam_flag(values, BEAM_FIRMWARE_PARAM)
    return ItemInfo(
        body=body,
        material=material,
        kind=kind,
        has_beam=bool(beam),
        firmware=firmware,
        firmware_name=read_item_firmware(item) if firmware else None,
        anointed=beam_flag(values, BEAM_ANOINTED_PARAM),
        shiny=beam_flag(values, BEAM_SHINY_PARAM),
        read_at=time.monotonic(),
    )


def is_complete(info: ItemInfo) -> bool:
    """Checks if there's anything left to learn. A fresh drop may not have its beam set up yet."""
    return info.kind is not None or (bool(info.body) and "/Gear/" not in info.body and "/Pickups/" not in info.body)


def matches_gear_filters(
    info: ItemInfo,
    gear_types: dict[str, BoolOption],
    manufacturers: dict[str, BoolOption],
    characters: dict[str, BoolOption],
) -> bool:
    """Checks if a piece of gear's type, manufacturer or character is selected in the given filters."""
    gear_type = get_gear_type(info.body)
    if gear_type is None:
        return False
    if gear_types[gear_type].value:
        return True

    # Class mods have a manufacturer in their material, but it doesn't mean anything to a player
    if gear_type == CLASS_MOD:
        character = get_character(info.body)
        return character is not None and characters[character].value
    manufacturer = get_manufacturer(info.body, info.material)
    return manufacturer is not None and manufacturers[manufacturer].value


def firmware_selected(info: ItemInfo, selected: dict[str, BoolOption]) -> bool:
    """Checks a pickup has firmware which counts. One we couldn't identify always does."""
    if not info.firmware:
        return False
    return info.firmware_name is None or selected[info.firmware_name].value


def should_hide(info: ItemInfo) -> bool:
    """Decides if a pickup should be hidden. Anything we don't recognize stays visible."""
    if "/Missions/" in info.body:
        return False

    if "/Gear/" in info.body:
        if not info.has_beam or info.kind not in rarity_options:
            return False
        if (
            (keep_firmware.value and firmware_selected(info, firmware_options))
            or (keep_anointed.value and info.anointed)
            or (keep_shiny.value and info.shiny)
        ):
            return False
        if rarity_options[info.kind].value:
            return True
        if is_protected(info.kind):
            return False
        return matches_gear_filters(info, gear_type_options, manufacturer_options, character_options)

    if info.body and "/Pickups/" not in info.body:
        return False
    return info.kind in pickup_options and pickup_options[info.kind].value


def should_highlight(info: ItemInfo) -> bool:
    """Decides if a pickup should be highlighted. Anything we don't recognize is left alone."""
    if "/Missions/" in info.body:
        return False

    if "/Gear/" in info.body:
        if not info.has_beam or info.kind not in highlight_rarity_options:
            return False
        if (
            (highlight_firmware.value and firmware_selected(info, highlight_firmware_options))
            or (highlight_anointed.value and info.anointed)
            or (highlight_shiny.value and info.shiny)
        ):
            return True
        return highlight_rarity_options[info.kind].value or matches_gear_filters(
            info,
            highlight_gear_type_options,
            highlight_manufacturer_options,
            highlight_character_options,
        )

    if info.body and "/Pickups/" not in info.body:
        return False
    return info.kind in highlight_pickup_options and highlight_pickup_options[info.kind].value


def set_item_hidden(item: UObject, hidden: bool) -> None:
    """Hides or shows a pickup, along with its beam."""
    item.SetActorHiddenInGame(hidden)
    if item.AttractEffectComponent:
        item.AttractEffectComponent.SetHiddenInGame(hidden, True)


def boost_beam(beam: UObject, key: int, kind: str | None) -> None:
    """Makes a beam much stronger, remembering how to put it back."""
    global beam_error_logged  # noqa: PLW0603

    boosted = boosted_beams.get(key)
    if boosted is None:
        color = read_beam_color(beam)
        if color is None:
            return
        scale = beam.RelativeScale3D
        boosted = BoostedBeam(
            color=color,
            kind=kind,
            was_legendary=read_beam_flag(beam, BEAM_LEGENDARY_PARAM),
            scale=(scale.X, scale.Y, scale.Z),
            boosted_color=(),
            boosted_size=0.0,
        )

    brightness = beam_intensity.value
    new_color = (*(value * brightness for value in boosted.color[:3]), boosted.color[3])
    new_size = beam_size.value
    if boosted.boosted_color == new_color and boosted.boosted_size == new_size:
        return

    beam.SetVariableLinearColor(BEAM_COLOR_PARAM, linear_color(new_color))
    beam.SetVariableBool(BEAM_LEGENDARY_PARAM, True)  # noqa: FBT003
    x, y, z = boosted.scale
    beam.SetRelativeScale3D(make_struct("Vector", X=x * new_size, Y=y * new_size, Z=z * new_size))

    boosted.boosted_color = new_color
    boosted.boosted_size = new_size
    boosted_beams[key] = boosted

    # We can't see the result, but we can at least see if the game took the value
    actual = read_beam_color(beam)
    if not beam_error_logged and (actual is None or not colors_match(actual, new_color)):
        beam_error_logged = True
        warning(f"[Ground Item Hider] The beam didn't take its new colour: {actual}")


def restore_beam(beam: UObject | None, key: int) -> None:
    """Puts a boosted beam back to how the game made it."""
    boosted = boosted_beams.pop(key, None)
    if boosted is None or not beam:
        return
    beam.SetVariableLinearColor(BEAM_COLOR_PARAM, linear_color(boosted.color))
    beam.SetVariableBool(BEAM_LEGENDARY_PARAM, boosted.was_legendary)
    x, y, z = boosted.scale
    beam.SetRelativeScale3D(make_struct("Vector", X=x, Y=y, Z=z))


def is_live_actor(actor: UObject) -> bool:
    """Checks an object from find_all is a real actor, which isn't on its way out."""
    return bool(
        actor
        and actor != actor.Class.ClassDefaultObject
        and not actor.IsActorBeingDestroyed(),
    )


def get_class(class_name: str) -> UObject:
    """Finds a class, once. They're native, so they stay loaded, and looking one up isn't free."""
    found = known_classes.get(class_name)
    if found is None:
        found = known_classes[class_name] = find_class(class_name)
    return found


def get_gameplay_statics() -> UObject:
    """Gets the object GameplayStatics' functions are called on."""
    return get_class("GameplayStatics").ClassDefaultObject


def get_actors(pc: UObject, class_name: str) -> list[UObject]:
    """
    Gets the actors of a class in the current world. find_all goes through every object in the
    engine instead, which is hundreds of thousands of them, so it's only the backup.
    """
    global actor_search_failed  # noqa: PLW0603

    # No controller while loading or at shutdown. Failing during a map change is no reason to stay
    # on the slow search for good either, so this tries again every time.
    if pc:
        try:
            found = get_gameplay_statics().GetAllActorsOfClass(pc, get_class(class_name), [])
            return list(found[1] if isinstance(found, tuple) else found)
        except Exception as ex:  # noqa: BLE001
            if not actor_search_failed:
                actor_search_failed = True
                warning(f"[Ground Item Hider] Falling back to the slow search: {ex}")
    return list(find_all(class_name, False))


def get_vending_machine_items(pc: UObject) -> set[int]:
    """Items of the day are pickups too, but they should never be touched. These rarely change."""
    global vending_items, last_vending  # noqa: PLW0603

    now = time.monotonic()
    if now - last_vending < VENDING_INTERVAL:
        return vending_items
    last_vending = now

    items: set[int] = set()
    for machine in get_actors(pc, "OakVendingMachine"):
        try:
            if is_live_actor(machine) and (item := machine.GetIOTDForPlayer(pc)):
                items.add(item._get_address())  # noqa: SLF001
        except Exception as ex:  # noqa: BLE001, PERF203
            warning(f"[Ground Item Hider] Skipping vending machine: {ex}")
    vending_items = items
    return items


def get_ground_items(pc: UObject) -> list[UObject]:
    """Gets every pickup currently lying in the world, checking each one properly."""
    vending = get_vending_machine_items(pc)
    items = []
    for item in get_actors(pc, "InventoryPickup"):
        # Objects can die mid scan during a map change, which shouldn't stop us seeing the rest
        try:
            if (
                is_live_actor(item)
                and item.RootPrimitiveComponent
                and item._get_address() not in vending  # noqa: SLF001
            ):
                items.append(item)
        except Exception as ex:  # noqa: BLE001
            warning(f"[Ground Item Hider] Skipping pickup: {ex}")
    return items


def get_state_revision() -> int:
    """Gets a number which changes with anything deciding what happens to a pickup."""
    global last_state, state_revision  # noqa: PLW0603

    state = (paused, *(option.value for option in filter_options))
    if state != last_state:
        last_state = state
        state_revision += 1
    return state_revision


def get_item_info(
    item: UObject,
    key: int,
    now: float,
    reads_left: int,
    deadline: float,
    check_boosts: bool,
) -> tuple[ItemInfo | None, int]:
    """Gets what's known about a pickup, reading it if there's still budget to. None: try later."""
    global scan_backlog  # noqa: PLW0603

    info = item_infos.get(key)

    boosted = boosted_beams.get(key)
    if boosted is not None and check_boosts:
        beam = item.AttractEffectComponent
        color = read_beam_color(beam) if beam else None
        if color is None or not colors_match(color, boosted.boosted_color):
            del boosted_beams[key]
            info = None

    if info is not None and now - info.read_at < INFO_MAX_AGE:
        return info, reads_left
    if reads_left <= 0 or time.perf_counter() > deadline:
        scan_backlog = True
        return info, reads_left

    info = read_item_info(item, key)
    if not is_complete(info):
        info.read_at = now - INFO_MAX_AGE + INCOMPLETE_RETRY
    item_infos[key] = info
    return info, reads_left - 1


def handle_item(
    item: UObject,
    key: int,
    state: int,
    now: float,
    reads_left: int,
    deadline: float,
    check_boosts: bool,
) -> int:
    """Does the full check of a pickup. Returns how many reads are left."""
    if not is_live_actor(item) or not item.RootPrimitiveComponent:
        skip_until[key] = now + SKIPPED_ITEM_RETRY
        return reads_left
    if key not in hidden_by_us and item.bHidden:
        skip_until[key] = now + SKIPPED_ITEM_RETRY
        return reads_left

    info, reads_left = get_item_info(item, key, now, reads_left, deadline, check_boosts)
    if info is None:
        return reads_left

    hide = not paused and filter_mode.value == MODE_HIDE and should_hide(info)
    if hide and key not in hidden_by_us:
        set_item_hidden(item, True)
        hidden_by_us.add(key)
    elif not hide and key in hidden_by_us:
        set_item_hidden(item, False)
        hidden_by_us.discard(key)

    highlight = not paused and filter_mode.value == MODE_HIGHLIGHT and should_highlight(info)
    if highlight:
        beam = item.AttractEffectComponent
        if beam:
            boost_beam(beam, key, info.kind)
        if key not in highlight_pointers:
            highlight_pointers[key] = WeakPointer(item)
    else:
        highlight_pointers.pop(key, None)
        if key in boosted_beams:
            restore_beam(item.AttractEffectComponent, key)

    if is_complete(info):
        decided_with[key] = state
    return reads_left


def refresh_radar_items() -> None:
    """Notes where the highlighted items are. They barely move, so this only happens every scan."""
    positions = []
    for pointer, kind in highlighted_items:
        item = pointer()
        if item is None:
            continue
        location = item.K2_GetActorLocation()
        positions.append((location.X, location.Y, kind))
    radar_items[:] = positions


def apply_filter() -> None:
    """Brings every pickup in the world in line with the current settings."""
    global highlighted_items, last_boost_check, scan_backlog  # noqa: PLW0603

    pc = get_pc()
    state = get_state_revision()
    now = time.monotonic()
    check_boosts = bool(boosted_beams) and now - last_boost_check >= BOOST_CHECK_INTERVAL
    if check_boosts:
        last_boost_check = now
    scan_backlog = False

    vending = get_vending_machine_items(pc)
    pickups = get_actors(pc, "InventoryPickup")
    # Starts after getting the list, or a slow list could leave no time to ever read a pickup
    deadline = time.perf_counter() + SCAN_TIME_LIMIT
    reads_left = MAX_READS_PER_SCAN
    alive: set[int] = set()
    for item in pickups:
        try:
            key = item_key(item)
            if key in vending:
                continue
            alive.add(key)

            if key in skip_until:
                if now < skip_until[key]:
                    continue
                del skip_until[key]

            # The usual case: nothing has changed, so don't go near it
            info = item_infos.get(key)
            if (
                info is not None
                and decided_with.get(key) == state
                and now - info.read_at < INFO_MAX_AGE
                and not (check_boosts and key in boosted_beams)
            ):
                continue

            reads_left = handle_item(item, key, state, now, reads_left, deadline, check_boosts)
        except Exception as ex:  # noqa: BLE001
            # It's probably on its way out. Either way, not worth a line in the log every scan.
            skip_until[item_key(item)] = now + SKIPPED_ITEM_RETRY
            warning(f"[Ground Item Hider] Skipping pickup: {ex}")

    # Forget about anything which was picked up or unloaded
    hidden_by_us.intersection_update(alive)
    for known in (boosted_beams, item_infos, decided_with, highlight_pointers, skip_until):
        for key in known.keys() - alive:
            del known[key]

    highlighted_items = [
        (pointer, item_infos[key].kind if key in item_infos else None)
        for key, pointer in highlight_pointers.items()
    ]
    refresh_radar_items()


def time_until_next_scan() -> float:
    """How long to wait between scans. A backlog goes first, and slow scans run less often."""
    if scan_backlog and not paused:
        return BACKLOG_INTERVAL
    return max(scan_interval.value, min(SLOWEST_SCAN_INTERVAL, last_scan_seconds * SCAN_TIME_SHARE))


def timed_scan() -> None:
    """Scans, and notes how long it took, so a slow one shows up in the log."""
    global slowest_scan_ms, last_slow_log, last_scan_seconds, scan_error_logged  # noqa: PLW0603

    start = time.perf_counter()
    try:
        apply_filter()
    except Exception as ex:  # noqa: BLE001
        if not scan_error_logged:
            scan_error_logged = True
            warning(f"[Ground Item Hider] A scan failed, trying again: {ex}")
    last_scan_seconds = time.perf_counter() - start
    taken = last_scan_seconds * 1000.0

    scan_times_ms.append(taken)
    del scan_times_ms[:-100]
    slowest_scan_ms = max(slowest_scan_ms, taken)

    now = time.monotonic()
    if taken >= SLOW_SCAN_MS and now - last_slow_log >= SLOW_SCAN_LOG_INTERVAL:
        last_slow_log = now
        info(f"[Ground Item Hider] Slow scan: {taken:.1f} ms, {len(item_infos)} items known")


def new_widget(path: str, outer: UObject) -> UObject:
    """Creates a new UMG object."""
    return construct_object(find_object("Class", path), outer)


def linear_color(rgba: tuple[float, float, float, float]) -> WrappedStruct:
    """Creates a linear colour struct."""
    return make_struct("LinearColor", R=rgba[0], G=rgba[1], B=rgba[2], A=rgba[3])


def wanted_banner_text() -> str:
    """Gets what the warning should currently say."""
    if filter_mode.value == MODE_HIGHLIGHT:
        count = len(highlight_pointers)
        return f"{BANNER_TEXT_HIGHLIGHT}: {count}" if count else BANNER_TEXT_HIGHLIGHT
    count = len(hidden_by_us)
    return f"{BANNER_TEXT}: ukryte {count}" if count else BANNER_TEXT


def set_game_font(text: UObject, size: int = BANNER_FONT_SIZE) -> None:
    """Uses the game's own font, if it's loaded. The default one is fine otherwise."""
    try:
        font = find_object("Font", BANNER_FONT)
        text.SetFont(make_struct("SlateFontInfo", FontObject=font, TypefaceFontName=BANNER_TYPEFACE, Size=size))
    except Exception:  # noqa: BLE001
        font_info = text.Font
        font_info.Size = size
        text.SetFont(font_info)


def menu_needs_restart() -> bool:
    """
    Checks if BL4 Mod Menu has just set up its page in the game's own menus. Paks only load at
    startup, so until the game's restarted, F7 can only open its basic panel.
    """
    link = sys.modules.get("bl4_mod_menu.uilink")
    status = getattr(link, "status", None)
    if status is None:
        return False
    try:
        return status().get("state") == "next_start"
    except Exception:  # noqa: BLE001
        return False


def add_restart_notice(tree: UObject, canvas: UObject) -> UObject:
    """Adds the box saying the game needs restarting, under the warning. Starts off hidden."""
    box = new_widget("/Script/UMG.Border", tree)
    box.SetBrushColor(linear_color(BANNER_BACKGROUND))
    box.SetPadding(make_struct("Margin", Left=12.0, Top=6.0, Right=12.0, Bottom=7.0))
    canvas.AddChild(box)

    top_right = make_struct("Vector2D", X=1.0, Y=0.0)
    slot = box.Slot
    slot.SetAnchors(make_struct("Anchors", Minimum=top_right, Maximum=top_right))
    slot.SetAlignment(top_right)
    slot.SetPosition(make_struct("Vector2D", X=-BANNER_MARGIN, Y=RESTART_NOTICE_TOP))
    slot.SetAutoSize(True)

    text = new_widget("/Script/UMG.TextBlock", tree)
    set_game_font(text, RESTART_NOTICE_FONT_SIZE)
    text.SetColorAndOpacity(make_struct("SlateColor", SpecifiedColor=linear_color(BANNER_COLOR)))
    text.SetText(RESTART_NOTICE_TEXT)
    text.SetVisibility(HIT_TEST_INVISIBLE)
    box.SetContent(text)
    box.SetVisibility(COLLAPSED)
    return box


def build_banner(pc: UObject) -> None:
    """Adds the warning to the top right of the screen. It never takes the mouse or any input."""
    global banner_widget, banner_owner, banner_text, banner_label, banner_mode  # noqa: PLW0603
    global restart_notice, restart_notice_shown  # noqa: PLW0603

    # A fresh name each time, reusing one from a removed widget which hasn't been collected yet
    # would make Unreal recycle that object in place. The viewport keeps the widget alive.
    name = f"{BANNER_NAME}_{time.monotonic_ns() % 10**12}"
    widget = construct_object(find_object("Class", "/Script/UMG.UserWidget"), pc, name)
    tree = new_widget("/Script/UMG.WidgetTree", widget)
    widget.WidgetTree = tree
    canvas = new_widget("/Script/UMG.CanvasPanel", tree)
    tree.RootWidget = canvas

    restart_notice = add_restart_notice(tree, canvas)
    restart_notice_shown = False

    box = new_widget("/Script/UMG.Border", tree)
    box.SetBrushColor(linear_color(BANNER_BACKGROUND))
    box.SetPadding(make_struct("Margin", Left=12.0, Top=6.0, Right=12.0, Bottom=7.0))
    box.SetVisibility(HIT_TEST_INVISIBLE)
    canvas.AddChild(box)

    top_right = make_struct("Vector2D", X=1.0, Y=0.0)
    slot = box.Slot
    slot.SetAnchors(make_struct("Anchors", Minimum=top_right, Maximum=top_right))
    slot.SetAlignment(top_right)
    slot.SetPosition(make_struct("Vector2D", X=-BANNER_MARGIN, Y=BANNER_MARGIN))
    slot.SetAutoSize(True)

    column = new_widget("/Script/UMG.VerticalBox", tree)
    box.SetContent(column)

    # A thin line along the top, in the mode's colour
    highlighting = filter_mode.value == MODE_HIGHLIGHT
    accent = new_widget("/Script/UMG.Border", tree)
    accent.SetBrushColor(linear_color(BANNER_COLOR_HIGHLIGHT if highlighting else BANNER_COLOR))
    column.AddChild(accent)
    accent.Slot.SetPadding(make_struct("Margin", Bottom=5.0))
    spacer = new_widget("/Script/UMG.Spacer", tree)
    spacer.SetSize(make_struct("Vector2D", X=1.0, Y=2.0))
    accent.SetContent(spacer)

    text = new_widget("/Script/UMG.TextBlock", tree)
    set_game_font(text)
    text.SetColorAndOpacity(make_struct("SlateColor", SpecifiedColor=linear_color(BANNER_TEXT_COLOR)))
    banner_text = wanted_banner_text()
    text.SetText(banner_text)
    text.SetVisibility(HIT_TEST_INVISIBLE)
    column.AddChild(text)

    widget.SetVisibility(HIT_TEST_INVISIBLE)
    widget.AddToViewport(BANNER_Z_ORDER)
    banner_widget = WeakPointer(widget)
    banner_owner = WeakPointer(pc)
    banner_label = text
    banner_mode = filter_mode.value


def remove_banner() -> None:
    """Removes the warning from the screen, if it's there."""
    global banner_widget, banner_owner  # noqa: PLW0603

    widget = banner_widget()
    banner_widget = WeakPointer()
    banner_owner = WeakPointer()
    if widget is not None:
        widget.RemoveFromParent()


def update_banner(pc: UObject) -> None:
    """Shows the warning while the filter is active. Changing map throws it away, so re-adds it."""
    global banner_error_logged, banner_text, restart_notice_shown  # noqa: PLW0603

    # The warning failing must never stop the filter itself
    try:
        if paused:
            remove_banner()
            return
        widget = banner_widget()
        if (
            widget is None
            or banner_owner() != pc
            or banner_mode != filter_mode.value
            or not widget.IsInViewport()
        ):
            remove_banner()
            build_banner(pc)

        wanted = wanted_banner_text()
        if wanted != banner_text:
            banner_text = wanted
            banner_label.SetText(wanted)

        needs_restart = menu_needs_restart()
        if needs_restart != restart_notice_shown:
            restart_notice_shown = needs_restart
            restart_notice.SetVisibility(HIT_TEST_INVISIBLE if needs_restart else COLLAPSED)
    except Exception as ex:  # noqa: BLE001
        if not banner_error_logged:
            banner_error_logged = True
            warning(f"[Ground Item Hider] Couldn't show the on screen warning: {ex}")


def round_brush(
    fill: tuple[float, float, float, float],
    outline: tuple[float, float, float, float] | None = None,
    outline_width: float = 0.0,
) -> WrappedStruct:
    """Creates a brush drawing a circle, which needs no textures from the game."""
    brush = make_struct("SlateBrush")
    brush.TintColor.SpecifiedColor = linear_color(fill)
    brush.DrawAs = DRAW_ROUNDED_BOX
    brush.OutlineSettings.RoundingType = ROUND_HALF_HEIGHT
    if outline is not None:
        brush.OutlineSettings.Width = outline_width
        brush.OutlineSettings.Color.SpecifiedColor = linear_color(outline)
    return brush


def place_widget(
    widget: UObject,
    anchor: tuple[float, float],
    alignment: tuple[float, float],
    position: tuple[float, float],
    size: tuple[float, float],
) -> None:
    """Sets where a widget sits in the canvas holding it."""
    point = make_struct("Vector2D", X=anchor[0], Y=anchor[1])
    slot = widget.Slot
    slot.SetAnchors(make_struct("Anchors", Minimum=point, Maximum=point))
    slot.SetAlignment(make_struct("Vector2D", X=alignment[0], Y=alignment[1]))
    slot.SetPosition(make_struct("Vector2D", X=position[0], Y=position[1]))
    slot.SetSize(make_struct("Vector2D", X=size[0], Y=size[1]))


def add_player_mark(tree: UObject, frame: UObject) -> None:
    """Shows where you are: the game's own radar arrow if it's loaded, otherwise a dot and a tick."""
    image = new_widget("/Script/UMG.Image", tree)
    try:
        image.SetBrushFromTexture(find_object("Texture2D", RADAR_ARROW), False)  # noqa: FBT003
        size = 26.0
    except Exception:  # noqa: BLE001
        image.SetBrush(round_brush(RADAR_PLAYER))
        size = 8.0
    frame.AddChild(image)
    place_widget(image, (0.5, 0.5), (0.5, 0.5), (0.0, 0.0), (size, size))
    image.SetVisibility(HIT_TEST_INVISIBLE)


def build_radar(pc: UObject) -> None:
    """Adds the radar under the warning. Like the warning, it never takes the mouse or any input."""
    global radar_widget, radar_owner, radar_markers, radar_markers_shown  # noqa: PLW0603
    global radar_marker_positions, radar_marker_kinds, radar_built_place  # noqa: PLW0603

    name = f"GroundItemHider_Radar_{time.monotonic_ns() % 10**12}"
    widget = construct_object(find_object("Class", "/Script/UMG.UserWidget"), pc, name)
    tree = new_widget("/Script/UMG.WidgetTree", widget)
    widget.WidgetTree = tree
    root = new_widget("/Script/UMG.CanvasPanel", tree)
    tree.RootWidget = root

    frame = new_widget("/Script/UMG.CanvasPanel", tree)
    root.AddChild(frame)
    if radar_place.value == RADAR_RIGHT:
        place_widget(
            frame,
            (1.0, 0.0),
            (1.0, 0.0),
            (-BANNER_MARGIN, RADAR_TOP_RIGHT),
            (RADAR_SIZE, RADAR_SIZE),
        )
    else:
        place_widget(
            frame,
            (0.0, 0.0),
            (0.0, 0.0),
            (BANNER_MARGIN, RADAR_TOP_LEFT),
            (RADAR_SIZE, RADAR_SIZE),
        )
    radar_built_place = radar_place.value

    def add_circle(brush: WrappedStruct, position: tuple[float, float], size: float) -> UObject:
        image = new_widget("/Script/UMG.Image", tree)
        image.SetBrush(brush)
        frame.AddChild(image)
        place_widget(image, (0.5, 0.5), (0.5, 0.5), position, (size, size))
        image.SetVisibility(HIT_TEST_INVISIBLE)
        return image

    add_circle(round_brush(RADAR_BACKGROUND, RADAR_RING, 2.0), (0.0, 0.0), RADAR_SIZE)
    add_circle(round_brush(RADAR_CLEAR, RADAR_INNER_RING, 1.0), (0.0, 0.0), RADAR_SIZE / 2)
    add_player_mark(tree, frame)

    # White, so each marker can take its rarity's colour. The outline stays black, on any background.
    marker_brush = round_brush(RADAR_PLAYER, RADAR_MARKER_OUTLINE, 2.0)
    radar_markers = []
    for _ in range(RADAR_MAX_MARKERS):
        marker = add_circle(marker_brush, (0.0, 0.0), RADAR_MARKER_SIZE)
        marker.SetVisibility(COLLAPSED)
        radar_markers.append(marker)
    radar_markers_shown = [False] * RADAR_MAX_MARKERS
    radar_marker_positions = [None] * RADAR_MAX_MARKERS
    radar_marker_kinds = [""] * RADAR_MAX_MARKERS

    widget.SetVisibility(HIT_TEST_INVISIBLE)
    widget.AddToViewport(RADAR_Z_ORDER)
    radar_widget = WeakPointer(widget)
    radar_owner = WeakPointer(pc)


def remove_radar() -> None:
    """Removes the radar from the screen, if it's there."""
    global radar_widget, radar_owner, radar_markers, radar_markers_shown  # noqa: PLW0603
    global radar_marker_positions  # noqa: PLW0603

    widget = radar_widget()
    radar_widget = WeakPointer()
    radar_owner = WeakPointer()
    radar_markers = []
    radar_markers_shown = []
    radar_marker_positions = []
    if widget is not None:
        widget.RemoveFromParent()


def radar_position(
    offset_x: float,
    offset_y: float,
    yaw: float,
    range_units: float,
) -> tuple[float, float]:
    """Finds where a world offset goes on the radar. Forward is up, far away stays on the rim."""
    radians = math.radians(yaw)
    forward = offset_x * math.cos(radians) + offset_y * math.sin(radians)
    right = -offset_x * math.sin(radians) + offset_y * math.cos(radians)

    edge = RADAR_SIZE / 2 - RADAR_MARKER_SIZE / 2
    scale = edge / range_units
    x, y = right * scale, -forward * scale
    distance = math.hypot(x, y)
    if distance > edge:
        x, y = x * edge / distance, y * edge / distance
    return x, y


def update_radar_markers(pc: UObject) -> None:
    """Moves the markers to where the highlighted items are, nearest ones first."""
    widget = radar_widget()
    pawn = pc.Pawn
    if widget is None or not pawn:
        return

    player = pawn.K2_GetActorLocation()
    offsets = [(x - player.X, y - player.Y, kind) for x, y, kind in radar_items]
    offsets.sort(key=lambda offset: math.hypot(offset[0], offset[1]))

    yaw = float(pc.GetControlRotation().Yaw)
    range_units = radar_range.value * 100.0
    for index, marker in enumerate(radar_markers):
        shown = index < len(offsets)
        if shown:
            offset_x, offset_y, kind = offsets[index]
            x, y = radar_position(offset_x, offset_y, yaw, range_units)
            position = (round(x), round(y))
            if position != radar_marker_positions[index]:
                radar_marker_positions[index] = position
                marker.Slot.SetPosition(make_struct("Vector2D", X=float(x), Y=float(y)))
            if kind != radar_marker_kinds[index]:
                radar_marker_kinds[index] = kind
                marker.SetColorAndOpacity(linear_color(MARKER_COLORS.get(kind, RADAR_MARKER_DEFAULT)))
        if shown != radar_markers_shown[index]:
            marker.SetVisibility(HIT_TEST_INVISIBLE if shown else COLLAPSED)
            radar_markers_shown[index] = shown


MARKER_COLORS = {kind: color for color, kind in reversed(BEAM_COLORS)}


def log_radar_error(ex: Exception) -> None:
    """Logs a problem with the radar, once. The radar failing must never stop the filter itself."""
    global radar_error_logged  # noqa: PLW0603

    if not radar_error_logged:
        radar_error_logged = True
        warning(f"[Ground Item Hider] Couldn't show the radar: {ex}")


def update_radar(pc: UObject) -> None:
    """Shows the radar in highlight mode. Changing map throws it away, so re-adds it."""
    try:
        if paused or filter_mode.value != MODE_HIGHLIGHT or not show_radar.value:
            remove_radar()
            return
        widget = radar_widget()
        if (
            widget is None
            or radar_owner() != pc
            or radar_built_place != radar_place.value
            or not widget.IsInViewport()
        ):
            remove_radar()
            build_radar(pc)
        update_radar_markers(pc)
    except Exception as ex:  # noqa: BLE001
        log_radar_error(ex)


# This runs every frame, Loot Magnet and BLImGui use the same hook as their game thread callback
@hook("/Script/Engine.CameraModifier:BlueprintModifyCamera", Type.POST_UNCONDITIONAL)
def on_tick(_obj: UObject, _args: WrappedStruct, _ret: Any, _func: BoundFunction) -> None:
    global last_scan, last_radar, last_widget_check  # noqa: PLW0603

    now = time.monotonic()
    if now - last_scan < time_until_next_scan():
        # Items don't turn up this often, but you can turn around much faster
        if radar_widget() is not None and now - last_radar >= RADAR_INTERVAL:
            last_radar = now
            pc = get_pc()
            if pc:
                try:
                    update_radar_markers(pc)
                except Exception as ex:  # noqa: BLE001
                    log_radar_error(ex)
        return
    last_scan = now

    pc = get_pc()
    if not pc:
        return
    if not paused:
        timed_scan()
    if now - last_widget_check >= WIDGET_CHECK_INTERVAL:
        last_widget_check = now
        update_banner(pc)
        update_radar(pc)


@keybind(
    "Toggle Item Hiding",
    key="F8",
    display_name="Włącz lub wstrzymaj filtr",
    description="Na chwilę wyłącza filtr, a kolejne naciśnięcie włącza go z powrotem.",
)
def toggle_hiding() -> None:
    global paused  # noqa: PLW0603

    paused = not paused
    apply_filter()
    pc = get_pc()
    if pc:
        update_banner(pc)
        update_radar(pc)
    info(f"[Ground Item Hider] {'Showing all loot' if paused else 'Filter back on'}")


@keybind(
    "Switch Filter Mode",
    display_name="Przełącz tryb filtra",
    description="Przełącza między ukrywaniem a podświetlaniem itemów.",
)
def switch_filter_mode() -> None:
    filter_mode.value = MODE_HIDE if filter_mode.value == MODE_HIGHLIGHT else MODE_HIGHLIGHT
    mod.save_settings()
    apply_filter()
    pc = get_pc()
    if pc:
        update_banner(pc)
        update_radar(pc)
    info(f"[Ground Item Hider] Filter mode: {filter_mode.value}")


@keybind(
    "Print Loot Info",
    display_name="Wypisz dane o lootcie",
    description="Wypisuje do konsoli, co filtr widzi na każdym itemie. Przydatne przy problemach.",
)
def print_loot_info() -> None:
    items = get_ground_items(get_pc())
    average = sum(scan_times_ms) / len(scan_times_ms) if scan_times_ms else 0.0
    info(
        f"[Ground Item Hider] {len(items)} items, {len(hidden_by_us)} hidden, scans: average"
        f" {average:.2f} ms, slowest {slowest_scan_ms:.2f} ms, slow search: {actor_search_failed}",
    )
    for item in items:
        key = item_key(item)
        loot = read_item_info(item, key)
        beam = item.AttractEffectComponent
        info(
            f"  kind={loot.kind}"
            f" type={get_gear_type(loot.body)}"
            f" character={get_character(loot.body)}"
            f" firmware={loot.firmware_name if loot.firmware_name else loot.firmware}"
            f" manufacturer={get_manufacturer(loot.body, loot.material)}"
            f" hide={should_hide(loot)}"
            f" highlight={should_highlight(loot)}"
            f" beam_color={read_beam_color(beam) if beam else None}"
            f" body={loot.body} material={loot.material}",
        )


def on_disable() -> None:
    global paused  # noqa: PLW0603

    # Don't leave anything invisible once the mod is off
    paused = True
    apply_filter()
    paused = False

    try:
        remove_banner()
        remove_radar()
    except Exception as ex:  # noqa: BLE001
        warning(f"[Ground Item Hider] Couldn't remove the on screen warning: {ex}")


def label(option: BaseOption, name: str, description: str) -> None:
    """Sets what an option is called in the menus."""
    option.display_name = option.description_title = name
    option.description = description


for key, option in rarity_options.items():
    label(option, RARITY_LABELS[key], f"Ukrywaj itemy: {RARITY_LABELS[key].lower()}.")
for key, option in highlight_rarity_options.items():
    label(option, RARITY_LABELS[key], f"Podświetlaj itemy: {RARITY_LABELS[key].lower()}.")
for key, option in manufacturer_options.items():
    label(option, key, f"Ukrywaj sprzęt firmy {key}.")
for key, option in highlight_manufacturer_options.items():
    label(option, key, f"Podświetlaj sprzęt firmy {key}.")
for key, option in gear_type_options.items():
    label(option, GEAR_TYPE_LABELS[key], f"Ukrywaj: {GEAR_TYPE_LABELS[key].lower()}.")
for key, option in highlight_gear_type_options.items():
    label(option, GEAR_TYPE_LABELS[key], f"Podświetlaj: {GEAR_TYPE_LABELS[key].lower()}.")
for key, option in character_options.items():
    label(option, key, f"Ukrywaj mody klasowe postaci {key}.")
for key, option in highlight_character_options.items():
    label(option, key, f"Podświetlaj mody klasowe postaci {key}.")
for key, option in firmware_options.items():
    label(option, FIRMWARE_NAMES[key], f"Zawsze pokazuj sprzęt z firmware {FIRMWARE_NAMES[key]}.")
for key, option in highlight_firmware_options.items():
    label(option, FIRMWARE_NAMES[key], f"Podświetlaj sprzęt z firmware {FIRMWARE_NAMES[key]}.")
for key, option in pickup_options.items():
    label(option, PICKUP_LABELS[key], f"Ukrywaj na ziemi: {PICKUP_LABELS[key].lower()}.")
for key, option in highlight_pickup_options.items():
    label(option, PICKUP_LABELS[key], f"Podświetlaj na ziemi: {PICKUP_LABELS[key].lower()}.")

label(
    filter_mode,
    "Tryb filtra",
    "Ukrywanie: wybrane itemy znikają z ziemi. Podświetlanie: wypada wszystko, a itemy wybrane w"
    " filtrach podświetlania dostają mocny beam i znacznik na radarze.",
)
label(keep_firmware, "Zawsze pokazuj firmware", "Nigdy nie ukrywaj sprzętu z firmware.")
label(keep_anointed, "Zawsze pokazuj namaszczone", "Nigdy nie ukrywaj sprzętu z anointmentem.")
label(keep_shiny, "Zawsze pokazuj błyszczące", "Nigdy nie ukrywaj sprzętu shiny.")
label(highlight_firmware, "Podświetlaj firmware", "Podświetlaj cały sprzęt z firmware.")
label(highlight_anointed, "Podświetlaj namaszczone", "Podświetlaj cały sprzęt z anointmentem.")
label(highlight_shiny, "Podświetlaj błyszczące", "Podświetlaj cały sprzęt shiny.")
label(beam_intensity, "Jasność beamu", "Ile razy jaśniejszy od zwykłego ma być beam.")
label(beam_size, "Rozmiar beamu", "Ile razy większy od zwykłego ma być beam.")
label(show_radar, "Pokazuj radar", "Mały radar w prawym górnym rogu, obracający się razem z Tobą.")
label(radar_place, "Pozycja radaru", "Gdzie na ekranie pokazywać radar podświetlonych itemów.")
label(radar_range, "Zasięg radaru", "Ile metrów do krawędzi radaru. Dalsze itemy zostają na krawędzi.")
label(scan_interval, "Częstość skanowania", "Sekundy między szukaniem nowego lootu. Filtr sam zwalnia, gdy gra tego potrzebuje.")

# What decides what happens to a pickup. The radar and scan settings only affect how it's shown.
filter_options = [
    filter_mode,
    *rarity_options.values(),
    *manufacturer_options.values(),
    *gear_type_options.values(),
    *character_options.values(),
    *pickup_options.values(),
    *firmware_options.values(),
    protected_rarity,
    keep_firmware,
    keep_anointed,
    keep_shiny,
    *highlight_rarity_options.values(),
    *highlight_manufacturer_options.values(),
    *highlight_gear_type_options.values(),
    *highlight_character_options.values(),
    *highlight_pickup_options.values(),
    *highlight_firmware_options.values(),
    highlight_firmware,
    highlight_anointed,
    highlight_shiny,
    beam_intensity,
    beam_size,
]

mod = build_mod(
    on_disable=on_disable,
    options=[
        filter_mode,
        NestedOption(
            "Hide By Rarity",
            children=list(rarity_options.values()),
            display_name="Ukrywaj: rzadkość",
            description="Które rzadkości ukrywać na ziemi.",
        ),
        NestedOption(
            "Hide By Manufacturer",
            children=list(manufacturer_options.values()),
            display_name="Ukrywaj: firmy",
            description="Sprzęt których firm ukrywać na ziemi.",
        ),
        NestedOption(
            "Hide By Item Type",
            children=list(gear_type_options.values()),
            display_name="Ukrywaj: typy itemów",
            description="Które typy sprzętu ukrywać na ziemi.",
        ),
        NestedOption(
            "Hide Class Mods By Character",
            children=list(character_options.values()),
            display_name="Ukrywaj: mody klasowe postaci",
            description="Mody klasowe których postaci ukrywać na ziemi.",
        ),
        NestedOption(
            "Hide Pickups",
            children=list(pickup_options.values()),
            display_name="Ukrywaj: amunicja, zdrowie i inne",
            description="Które przedmioty użytkowe ukrywać na ziemi.",
        ),
        protected_rarity,
        keep_firmware,
        NestedOption(
            "Keep Which Firmware",
            children=list(firmware_options.values()),
            display_name="Który firmware zawsze pokazywać",
            description=(
                "Sprzęt z odznaczonym firmware nie ma już wyjątku i podlega zwykłym filtrom."
                " Działa, gdy włączone jest Zawsze pokazuj firmware."
            ),
        ),
        keep_anointed,
        keep_shiny,
        NestedOption(
            "Highlight Filters",
            children=[
                NestedOption(
                    "Highlight By Rarity",
                    children=list(highlight_rarity_options.values()),
                    display_name="Rzadkość",
                    description="Które rzadkości podświetlać.",
                ),
                NestedOption(
                    "Highlight By Manufacturer",
                    children=list(highlight_manufacturer_options.values()),
                    display_name="Firmy",
                    description="Sprzęt których firm podświetlać.",
                ),
                NestedOption(
                    "Highlight By Item Type",
                    children=list(highlight_gear_type_options.values()),
                    display_name="Typy itemów",
                    description="Które typy sprzętu podświetlać.",
                ),
                NestedOption(
                    "Highlight Class Mods By Character",
                    children=list(highlight_character_options.values()),
                    display_name="Mody klasowe postaci",
                    description="Mody klasowe których postaci podświetlać.",
                ),
                NestedOption(
                    "Highlight Pickups",
                    children=list(highlight_pickup_options.values()),
                    display_name="Amunicja, zdrowie i inne",
                    description="Które przedmioty użytkowe podświetlać.",
                ),
                highlight_firmware,
                NestedOption(
                    "Highlight Which Firmware",
                    children=list(highlight_firmware_options.values()),
                    display_name="Który firmware podświetlać",
                    description="Działa, gdy włączone jest Podświetlaj firmware.",
                ),
                highlight_anointed,
                highlight_shiny,
                beam_intensity,
                beam_size,
                show_radar,
                radar_place,
                radar_range,
            ],
            display_name="Podświetlanie: filtry i wygląd",
            description="Co podświetlać w trybie podświetlania, i jak mocno.",
        ),
        scan_interval,
    ],
)


def fix_old_spinner_values() -> None:
    """Settings saved before the menus were translated hold values which no longer exist."""
    for option in (filter_mode, protected_rarity, radar_place):
        if option.value not in option.choices:
            option.value = option.default_value


fix_old_spinner_values()
