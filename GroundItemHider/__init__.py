"""
Ground Item Hider: a client-side loot filter for Borderlands 4.

Instead of teleporting or deleting loot, this only hides it. The pickup stays exactly where it
dropped, so turning the filter off brings it straight back.

An item is hidden if its rarity, manufacturer or type is selected. Items we can't recognize always
stay visible.

In highlight mode nothing is hidden. The selected items instead get a much stronger loot beam, and a
marker on a small radar. The game has no minimap of its own, and its compass is fed by native code
we can't reach, so the radar is our own widget.

Reading rarity from the loot beam is adapted from BL4 Loot Filter by Lango (GPL-3.0), which credits
SlippyCheeze for the original logic. https://github.com/jlangowells/bl4_loot_filter
The beam colour palettes and body paths were cross-checked with Loot Magnet by max0n4ik.
https://github.com/max0n4ik/LootMagnet
"""

from __future__ import annotations

import math
import re
import struct
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
from unrealsdk import construct_object, find_all, find_object, make_struct
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
BANNER_FONT_SIZE = 20
HIT_TEST_INVISIBLE = 3
# UMG colours are linear
BANNER_BACKGROUND = (0.0012, 0.0052, 0.0098, 0.88)
BANNER_COLOR = (1.0, 0.45, 0.02, 1.0)
BANNER_TEXT_HIGHLIGHT = "FILTR AKTYWNY: PODSWIETLANIE"

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

COLLAPSED = 1
DRAW_ROUNDED_BOX = 4
ROUND_HALF_HEIGHT = 1
RADAR_Z_ORDER = 19
RADAR_SIZE = 180.0
RADAR_TOP = 78.0  # Leaves room for the banner above it
RADAR_INTERVAL = 0.05
RADAR_MARKER_SIZE = 16.0
RADAR_MAX_MARKERS = 32
RADAR_BACKGROUND = (0.0012, 0.0052, 0.0098, 0.75)
RADAR_RING = (0.13, 0.62, 1.0, 1.0)
RADAR_PLAYER = (1.0, 1.0, 1.0, 1.0)
RADAR_MARKER_FILL = (1.0, 0.0, 0.45, 1.0)
RADAR_MARKER_OUTLINE = (1.0, 1.0, 1.0, 1.0)

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
    identifier="Scan Interval",
    value=1.0,
    min_value=0.25,
    max_value=5.0,
    step=0.25,
    is_integer=False,
    description="Seconds between looking for new loot. Raise this if you notice stutters.",
)

paused: bool = False
last_scan: float = 0.0
# Only ever unhide what we hid ourselves, the game hides some pickups for its own reasons.
hidden_by_us: set[str] = set()
reported_colors: set[tuple[float, ...]] = set()
banner_widget: WeakPointer = WeakPointer()
banner_owner: WeakPointer = WeakPointer()
banner_error_logged: bool = False
banner_text: str = ""


@dataclass
class BoostedBeam:
    """What a beam looked like before we boosted it, and what we changed it to."""

    color: tuple[float, ...]
    kind: str | None
    was_legendary: bool
    scale: tuple[float, float, float]
    boosted_color: tuple[float, ...]
    boosted_size: float


boosted_beams: dict[str, BoostedBeam] = {}
beam_error_logged: bool = False
highlighted_items: list[WeakPointer] = []
last_radar: float = 0.0
radar_widget: WeakPointer = WeakPointer()
radar_owner: WeakPointer = WeakPointer()
radar_markers: list[UObject] = []
radar_markers_shown: list[bool] = []
radar_error_logged: bool = False


def classify_color(color: tuple[float, ...]) -> str | None:
    """Finds what a beam colour stands for. There's no nearest match, unknowns return None."""
    if not all(math.isfinite(value) for value in color):
        return None
    for expected, kind in BEAM_COLORS:
        if all(abs(a - b) <= BEAM_COLOR_TOLERANCE for a, b in zip(color, expected, strict=True)):
            return kind
    return None


def read_beam_param(beam: UObject, wanted: str, size: int) -> bytes | None:
    """Reads the raw value of a beam parameter, or None if it isn't set."""
    data = bytes(beam.OverrideParameters.ParameterData)
    for param in beam.OverrideParameters.SortedParameterOffsets:
        # A parameter which isn't set has a negative offset, which must not count as being true
        if str(param.Name) == wanted and 0 <= param.Offset and param.Offset + size <= len(data):
            return data[param.Offset : param.Offset + size]
    return None


def read_beam_color(beam: UObject) -> tuple[float, ...] | None:
    """Reads the beam's current colour."""
    raw = read_beam_param(beam, BEAM_COLOR_PARAM, 16)
    return None if raw is None else struct.unpack("<4f", raw)


def read_beam_flag(beam: UObject, name: str) -> bool:
    """Reads one of the beam's flags."""
    raw = read_beam_param(beam, name, 4)
    return raw is not None and raw != NIAGARA_FALSE


def colors_match(first: tuple[float, ...], second: tuple[float, ...]) -> bool:
    """Checks if two colours are the same, give or take float precision."""
    return all(abs(a - b) <= BEAM_BOOST_TOLERANCE for a, b in zip(first, second, strict=True))


def get_beam_kind(beam: UObject, key: str) -> str | None:
    """Gets what a beam's colour stands for, seeing through our own boost."""
    color = read_beam_color(beam)
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


def is_protected(rarity: str) -> bool:
    """Checks if a rarity is exempt from the manufacturer and item type filters."""
    if protected_rarity.value == NO_PROTECTION:
        return False
    protected = next(key for key, label in RARITY_LABELS.items() if label == protected_rarity.value)
    return RARITY_ORDER.index(rarity) >= RARITY_ORDER.index(protected)


def matches_gear_filters(
    body: str,
    material: str,
    gear_types: dict[str, BoolOption],
    manufacturers: dict[str, BoolOption],
) -> bool:
    """Checks if a piece of gear's type or manufacturer is selected in the given filters."""
    gear_type = get_gear_type(body)
    if gear_type is None:
        return False
    if gear_types[gear_type].value:
        return True

    # Class mods have a manufacturer in their material, but it doesn't mean anything to a player
    if gear_type == CLASS_MOD:
        return False
    manufacturer = get_manufacturer(body, material)
    return manufacturer is not None and manufacturers[manufacturer].value


def get_pickup_kind(material: str, beam: UObject | None, key: str) -> str | None:
    """Gets the kind of a consumable, from its beam or else its material."""
    kind = get_beam_kind(beam, key) if beam else None
    if kind is None:
        for part in material.split("_"):
            kind = PICKUP_MATERIAL_NAMES.get(part)
            if kind is not None:
                break
    return kind


def should_hide_gear(body: str, material: str, beam: UObject | None, key: str) -> bool:
    """Decides if a piece of gear should be hidden."""
    if not beam:
        return False
    rarity = get_beam_kind(beam, key)
    if rarity not in rarity_options:
        return False
    for option, flag in (
        (keep_firmware, BEAM_FIRMWARE_PARAM),
        (keep_anointed, BEAM_ANOINTED_PARAM),
        (keep_shiny, BEAM_SHINY_PARAM),
    ):
        if option.value and read_beam_flag(beam, flag):
            return False

    if rarity_options[rarity].value:
        return True
    if is_protected(rarity):
        return False
    return matches_gear_filters(body, material, gear_type_options, manufacturer_options)


def should_hide(item: UObject) -> bool:
    """Decides if a pickup should be hidden. Anything we don't recognize stays visible."""
    key = str(item)
    body = str(item.BodyData) if item.BodyData else ""
    if "/Missions/" in body:
        return False

    material = get_material_name(item)
    beam = item.AttractEffectComponent

    if "/Gear/" in body:
        return should_hide_gear(body, material, beam, key)
    if body and "/Pickups/" not in body:
        return False

    kind = get_pickup_kind(material, beam, key)
    return kind in pickup_options and pickup_options[kind].value


def should_highlight(item: UObject) -> bool:
    """Decides if a pickup should be highlighted. Anything we don't recognize is left alone."""
    key = str(item)
    body = str(item.BodyData) if item.BodyData else ""
    if "/Missions/" in body:
        return False

    material = get_material_name(item)
    beam = item.AttractEffectComponent

    if "/Gear/" in body:
        if not beam:
            return False
        rarity = get_beam_kind(beam, key)
        if rarity not in highlight_rarity_options:
            return False
        for option, flag in (
            (highlight_firmware, BEAM_FIRMWARE_PARAM),
            (highlight_anointed, BEAM_ANOINTED_PARAM),
            (highlight_shiny, BEAM_SHINY_PARAM),
        ):
            if option.value and read_beam_flag(beam, flag):
                return True
        return highlight_rarity_options[rarity].value or matches_gear_filters(
            body,
            material,
            highlight_gear_type_options,
            highlight_manufacturer_options,
        )
    if body and "/Pickups/" not in body:
        return False

    kind = get_pickup_kind(material, beam, key)
    return kind in highlight_pickup_options and highlight_pickup_options[kind].value


def set_item_hidden(item: UObject, hidden: bool) -> None:
    """Hides or shows a pickup, along with its beam."""
    item.SetActorHiddenInGame(hidden)
    if item.AttractEffectComponent:
        item.AttractEffectComponent.SetHiddenInGame(hidden, True)


def boost_beam(beam: UObject, key: str) -> None:
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
            kind=classify_color(color),
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


def restore_beam(beam: UObject | None, key: str) -> None:
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


def get_vending_machine_items() -> list[UObject]:
    """Items of the day are pickups too, but they should never be touched."""
    pc = get_pc()
    items = []
    for machine in find_all("OakVendingMachine", False):
        try:
            if is_live_actor(machine) and (item := machine.GetIOTDForPlayer(pc)):
                items.append(item)
        except Exception as ex:  # noqa: BLE001, PERF203
            warning(f"[Ground Item Hider] Skipping vending machine: {ex}")
    return items


def get_ground_items() -> list[UObject]:
    """Gets every pickup currently lying in the world."""
    vending = get_vending_machine_items()
    items = []
    for item in find_all("InventoryPickup", False):
        # Objects can die mid scan during a map change, which shouldn't stop us seeing the rest
        try:
            if is_live_actor(item) and item.RootPrimitiveComponent and item not in vending:
                items.append(item)
        except Exception as ex:  # noqa: BLE001, PERF203
            warning(f"[Ground Item Hider] Skipping pickup: {ex}")
    return items


def apply_filter() -> None:
    """Brings every pickup in the world in line with the current settings."""
    global highlighted_items  # noqa: PLW0603

    hiding = not paused and filter_mode.value == MODE_HIDE
    highlighting = not paused and filter_mode.value == MODE_HIGHLIGHT

    alive: set[str] = set()
    highlighted: list[WeakPointer] = []
    for item in get_ground_items():
        key = str(item)
        alive.add(key)
        try:
            if key not in hidden_by_us and item.bHidden:
                continue

            hide = hiding and should_hide(item)
            if hide and key not in hidden_by_us:
                set_item_hidden(item, True)
                hidden_by_us.add(key)
            elif not hide and key in hidden_by_us:
                set_item_hidden(item, False)
                hidden_by_us.discard(key)

            beam = item.AttractEffectComponent
            if highlighting and should_highlight(item):
                if beam:
                    boost_beam(beam, key)
                highlighted.append(WeakPointer(item))
            else:
                restore_beam(beam, key)
        except Exception as ex:  # noqa: BLE001
            warning(f"[Ground Item Hider] Skipping {key}: {ex}")

    # Forget about anything which was picked up or unloaded
    hidden_by_us.intersection_update(alive)
    for key in boosted_beams.keys() - alive:
        del boosted_beams[key]
    highlighted_items = highlighted


def new_widget(path: str, outer: UObject) -> UObject:
    """Creates a new UMG object."""
    return construct_object(find_object("Class", path), outer)


def linear_color(rgba: tuple[float, float, float, float]) -> WrappedStruct:
    """Creates a linear colour struct."""
    return make_struct("LinearColor", R=rgba[0], G=rgba[1], B=rgba[2], A=rgba[3])


def wanted_banner_text() -> str:
    """Gets what the warning should currently say."""
    return BANNER_TEXT_HIGHLIGHT if filter_mode.value == MODE_HIGHLIGHT else BANNER_TEXT


def build_banner(pc: UObject) -> None:
    """Adds the warning to the top right of the screen. It never takes the mouse or any input."""
    global banner_widget, banner_owner, banner_text  # noqa: PLW0603

    # A fresh name each time, reusing one from a removed widget which hasn't been collected yet
    # would make Unreal recycle that object in place. The viewport keeps the widget alive.
    name = f"{BANNER_NAME}_{time.monotonic_ns() % 10**12}"
    widget = construct_object(find_object("Class", "/Script/UMG.UserWidget"), pc, name)
    tree = new_widget("/Script/UMG.WidgetTree", widget)
    widget.WidgetTree = tree
    canvas = new_widget("/Script/UMG.CanvasPanel", tree)
    tree.RootWidget = canvas

    box = new_widget("/Script/UMG.Border", tree)
    box.SetBrushColor(linear_color(BANNER_BACKGROUND))
    box.SetPadding(make_struct("Margin", Left=16.0, Top=8.0, Right=16.0, Bottom=8.0))
    box.SetVisibility(HIT_TEST_INVISIBLE)
    canvas.AddChild(box)

    top_right = make_struct("Vector2D", X=1.0, Y=0.0)
    slot = box.Slot
    slot.SetAnchors(make_struct("Anchors", Minimum=top_right, Maximum=top_right))
    slot.SetAlignment(top_right)
    slot.SetPosition(make_struct("Vector2D", X=-BANNER_MARGIN, Y=BANNER_MARGIN))
    slot.SetAutoSize(True)

    text = new_widget("/Script/UMG.TextBlock", tree)
    font = text.Font
    font.Size = BANNER_FONT_SIZE
    text.SetFont(font)
    text.SetColorAndOpacity(make_struct("SlateColor", SpecifiedColor=linear_color(BANNER_COLOR)))
    text.SetText(wanted_banner_text())
    text.SetVisibility(HIT_TEST_INVISIBLE)
    box.SetContent(text)

    widget.SetVisibility(HIT_TEST_INVISIBLE)
    widget.AddToViewport(BANNER_Z_ORDER)
    banner_widget = WeakPointer(widget)
    banner_owner = WeakPointer(pc)
    banner_text = wanted_banner_text()


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
    global banner_error_logged  # noqa: PLW0603

    # The warning failing must never stop the filter itself
    try:
        if paused:
            remove_banner()
            return
        widget = banner_widget()
        if (
            widget is None
            or banner_owner() != pc
            or banner_text != wanted_banner_text()
            or not widget.IsInViewport()
        ):
            remove_banner()
            build_banner(pc)
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


def build_radar(pc: UObject) -> None:
    """Adds the radar under the warning. Like the warning, it never takes the mouse or any input."""
    global radar_widget, radar_owner, radar_markers, radar_markers_shown  # noqa: PLW0603

    name = f"GroundItemHider_Radar_{time.monotonic_ns() % 10**12}"
    widget = construct_object(find_object("Class", "/Script/UMG.UserWidget"), pc, name)
    tree = new_widget("/Script/UMG.WidgetTree", widget)
    widget.WidgetTree = tree
    root = new_widget("/Script/UMG.CanvasPanel", tree)
    tree.RootWidget = root

    frame = new_widget("/Script/UMG.CanvasPanel", tree)
    root.AddChild(frame)
    place_widget(
        frame,
        (1.0, 0.0),
        (1.0, 0.0),
        (-BANNER_MARGIN, RADAR_TOP),
        (RADAR_SIZE, RADAR_SIZE),
    )

    def add_circle(brush: WrappedStruct, position: tuple[float, float], size: float) -> UObject:
        image = new_widget("/Script/UMG.Image", tree)
        image.SetBrush(brush)
        frame.AddChild(image)
        place_widget(image, (0.5, 0.5), (0.5, 0.5), position, (size, size))
        image.SetVisibility(HIT_TEST_INVISIBLE)
        return image

    add_circle(round_brush(RADAR_BACKGROUND, RADAR_RING, 3.0), (0.0, 0.0), RADAR_SIZE)
    # You're the dot in the middle, and the tick above it is where you're looking
    add_circle(round_brush(RADAR_PLAYER), (0.0, 0.0), 10.0)
    add_circle(round_brush(RADAR_PLAYER), (0.0, -14.0), 5.0)

    marker_brush = round_brush(RADAR_MARKER_FILL, RADAR_MARKER_OUTLINE, 2.0)
    radar_markers = []
    for _ in range(RADAR_MAX_MARKERS):
        marker = add_circle(marker_brush, (0.0, 0.0), RADAR_MARKER_SIZE)
        marker.SetVisibility(COLLAPSED)
        radar_markers.append(marker)
    radar_markers_shown = [False] * RADAR_MAX_MARKERS

    widget.SetVisibility(HIT_TEST_INVISIBLE)
    widget.AddToViewport(RADAR_Z_ORDER)
    radar_widget = WeakPointer(widget)
    radar_owner = WeakPointer(pc)


def remove_radar() -> None:
    """Removes the radar from the screen, if it's there."""
    global radar_widget, radar_owner, radar_markers, radar_markers_shown  # noqa: PLW0603

    widget = radar_widget()
    radar_widget = WeakPointer()
    radar_owner = WeakPointer()
    radar_markers = []
    radar_markers_shown = []
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
    """Moves the markers to where the highlighted items currently are, nearest ones first."""
    widget = radar_widget()
    pawn = pc.Pawn
    if widget is None or not pawn:
        return

    player = pawn.K2_GetActorLocation()
    offsets = []
    for pointer in highlighted_items:
        item = pointer()
        if item is None:
            continue
        location = item.K2_GetActorLocation()
        offsets.append((location.X - player.X, location.Y - player.Y))
    offsets.sort(key=lambda offset: math.hypot(*offset))

    yaw = float(pc.GetControlRotation().Yaw)
    range_units = radar_range.value * 100.0
    for index, marker in enumerate(radar_markers):
        shown = index < len(offsets)
        if shown:
            x, y = radar_position(*offsets[index], yaw, range_units)
            marker.Slot.SetPosition(make_struct("Vector2D", X=round(x, 1), Y=round(y, 1)))
        if shown != radar_markers_shown[index]:
            marker.SetVisibility(HIT_TEST_INVISIBLE if shown else COLLAPSED)
            radar_markers_shown[index] = shown


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
        if widget is None or radar_owner() != pc or not widget.IsInViewport():
            remove_radar()
            build_radar(pc)
        update_radar_markers(pc)
    except Exception as ex:  # noqa: BLE001
        log_radar_error(ex)


# This runs every frame, Loot Magnet and BLImGui use the same hook as their game thread callback
@hook("/Script/Engine.CameraModifier:BlueprintModifyCamera", Type.POST_UNCONDITIONAL)
def on_tick(_obj: UObject, _args: WrappedStruct, _ret: Any, _func: BoundFunction) -> None:
    global last_scan, last_radar  # noqa: PLW0603

    now = time.monotonic()
    if now - last_scan < scan_interval.value:
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
    update_banner(pc)
    if not paused:
        apply_filter()
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
    items = get_ground_items()
    info(f"[Ground Item Hider] {len(items)} items, {len(hidden_by_us)} hidden")
    for item in items:
        body = str(item.BodyData) if item.BodyData else ""
        material = get_material_name(item)
        beam = item.AttractEffectComponent
        info(
            f"  kind={get_beam_kind(beam, str(item)) if beam else None}"
            f" type={get_gear_type(body)}"
            f" manufacturer={get_manufacturer(body, material)}"
            f" hide={should_hide(item)}"
            f" highlight={should_highlight(item)}"
            f" beam_color={read_beam_color(beam) if beam else None}"
            f" body={body} material={material}",
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
label(radar_range, "Zasięg radaru", "Ile metrów do krawędzi radaru. Dalsze itemy zostają na krawędzi.")
label(scan_interval, "Częstość skanowania", "Sekundy między szukaniem lootu. Zwiększ przy przycięciach.")

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
            "Hide Pickups",
            children=list(pickup_options.values()),
            display_name="Ukrywaj: amunicja, zdrowie i inne",
            description="Które przedmioty użytkowe ukrywać na ziemi.",
        ),
        protected_rarity,
        keep_firmware,
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
                    "Highlight Pickups",
                    children=list(highlight_pickup_options.values()),
                    display_name="Amunicja, zdrowie i inne",
                    description="Które przedmioty użytkowe podświetlać.",
                ),
                highlight_firmware,
                highlight_anointed,
                highlight_shiny,
                beam_intensity,
                beam_size,
                show_radar,
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
    for option in (filter_mode, protected_rarity):
        if option.value not in option.choices:
            option.value = option.default_value


fix_old_spinner_values()
