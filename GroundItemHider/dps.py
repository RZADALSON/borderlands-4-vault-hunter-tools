"""
The DPS meter: shows the damage you deal per second, in a small window on screen.

The game tells each character about every hit it deals, see native.py. Only your own character is
listened to, so it's cheap, and it's your damage only. The game only does this where the damage is
worked out, so it works solo and when hosting. A co-op guest doesn't get told anything.

The window is plain UMG built in code, like the notices in bl4-fix by flameaway.
https://github.com/flameaway/bl4-fix
"""

from __future__ import annotations

import ctypes
import struct
import time
from dataclasses import dataclass
from typing import Any

from mods_base import BoolOption, SliderOption, get_pc, hook, keybind
from unrealsdk import construct_object, find_object, make_struct
from unrealsdk.hooks import Block, Type
from unrealsdk.logging import error, info
from unrealsdk.unreal import BoundFunction, UObject, WeakPointer, WrappedStruct

from . import meter, native
from .localized import Text, label, localized_spinner, say

LOG_TAG = "[DPS Meter]"

RESET_AFTER_IDLE = "idle"
RESET_BY_HAND = "manual"

how_to_count = label(
    localized_spinner(
        "How To Count",
        meter.MODE_FIGHT,
        {
            meter.MODE_FIGHT: ("Cała walka", "Whole fight"),
            meter.MODE_WINDOW: ("Ostatnie sekundy", "Last few seconds"),
        },
    ),
    ("Liczenie DPS", "DPS calculation"),
    (
        "Cała walka: wszystkie obrażenia podzielone przez czas od pierwszego do ostatniego trafienia."
        " Ostatnie sekundy: tylko obrażenia z ostatnich kilku sekund, więc od razu widać zmianę broni albo buffa.",
        "Whole fight: all your damage divided by the time from your first hit to your last."
        " Last few seconds: only the damage from the last few seconds, so a new weapon or buff shows up right away.",
    ),
)
window_seconds = label(
    SliderOption(identifier="Window Seconds", value=5.0, min_value=1.0, max_value=60.0, step=1.0, is_integer=False),
    ("Liczba sekund", "Number of seconds"),
    ("Z ilu ostatnich sekund liczyć DPS.", "How many seconds back to count."),
)
window_seconds.greyed_when = lambda: how_to_count.key != meter.MODE_WINDOW
when_to_reset = label(
    localized_spinner(
        "When To Reset",
        RESET_AFTER_IDLE,
        {
            RESET_AFTER_IDLE: ("Automatyczny", "Automatic"),
            RESET_BY_HAND: ("Tylko klawiszem", "Only with the key"),
        },
    ),
    ("Reset licznika", "Meter reset"),
    (
        "Automatyczny: licznik zeruje się, gdy przez podany czas nikogo nie trafisz."
        " Tylko klawiszem: zeruje go tylko klawisz resetu, domyślnie F6.",
        "Automatic: the meter goes back to zero once you haven't hit anything for the time below."
        " Only with the key: just the reset key does that, F6 by default.",
    ),
)
reset_seconds = label(
    SliderOption(identifier="Reset After Seconds", value=5.0, min_value=1.0, max_value=60.0, step=1.0, is_integer=False),
    ("Reset po (sekundy)", "Reset after (seconds)"),
    ("Po tylu sekundach bez trafienia licznik się zeruje.", "The meter resets after this many seconds without a hit."),
)
reset_seconds.greyed_when = lambda: when_to_reset.key != RESET_AFTER_IDLE
count_over_time = label(
    BoolOption("Count Damage Over Time", True),
    ("Obrażenia w czasie", "Damage over time"),
    ("Podpalenie, korozja i podobne.", "Burning, corrosion and so on."),
)
count_companions = label(
    BoolOption("Count Companions", True),
    ("Obrażenia towarzyszy", "Companion damage"),
    (
        "Trafienia, które gra zalicza Twojej postaci, ale zadało je coś innego, np. przywołaniec.",
        "Hits the game credits to your character but something else dealt, like a summon.",
    ),
)
show_window = label(
    BoolOption("Show Window", True),
    ("Pokazuj licznik", "Show the meter"),
    ("Po wyłączeniu licznik znika z ekranu, ale liczy dalej.", "Turned off, it leaves the screen but keeps counting."),
)
show_details = label(
    BoolOption("Show Details", True),
    ("Szczegóły", "Details"),
    ("Suma obrażeń, czas, krytyki, najlepsze trafienie i zabójstwa.", "Total damage, time, crits, best hit and kills."),
)
show_last_fight = label(
    BoolOption("Show Last Fight", True),
    ("Ostatnia walka", "Last fight"),
    ("Wynik poprzedniej walki pod licznikiem.", "The previous fight's result under the meter."),
)
window_x = label(
    SliderOption(identifier="Window X", value=98.5, min_value=0.0, max_value=100.0, step=0.5, is_integer=False),
    ("Pozycja w poziomie", "Horizontal position"),
    ("0 to lewa krawędź ekranu, 100 prawa.", "0 is the left edge of the screen, 100 the right."),
)
window_y = label(
    SliderOption(identifier="Window Y", value=26.0, min_value=0.0, max_value=100.0, step=0.5, is_integer=False),
    ("Pozycja w pionie", "Vertical position"),
    ("0 to góra ekranu, 100 dół.", "0 is the top of the screen, 100 the bottom."),
)
font_size = label(
    SliderOption(identifier="Font Size", value=28, min_value=10, max_value=48, step=1),
    ("Rozmiar", "Size"),
    ("Wielkość głównej liczby. Szczegóły są mniejsze.", "The size of the main number. The details are smaller."),
)
STYLE_GAME = "game"
STYLE_COMPACT = "compact"
STYLE_MINIMAL = "minimal"
STYLE_NEON = "neon"
window_style = label(
    localized_spinner(
        "Window Style",
        STYLE_GAME,
        {
            STYLE_GAME: ("Jak w grze", "Like the game"),
            STYLE_COMPACT: ("Kompaktowy", "Compact"),
            STYLE_MINIMAL: ("Sam tekst", "Text only"),
            STYLE_NEON: ("Neon", "Neon"),
        },
    ),
    ("Styl", "Style"),
    (
        "Jak w grze: kolory interfejsu gry. Kompaktowy: to samo, ale szczegóły w jednej linii."
        " Sam tekst: bez tła. Neon: jasne kolory.",
        "Like the game: the game's interface colours. Compact: the same, with the details on one line."
        " Text only: no background. Neon: bright colours.",
    ),
)
RELOAD_OPTIONS = (window_x, window_y, font_size)
WINDOW_OPTIONS = (window_style, show_details, show_last_fight, window_x, window_y, font_size)
for option in WINDOW_OPTIONS:
    option.greyed_when = lambda: not show_window.value

# --- What the game tells us -----------------------------------------------------------------------
HOSTILE = 2  # ETeamAttitude
ROLE_AUTHORITY = 3  # ENetRole
BIND_CHECK_INTERVAL = 0.5
UPDATE_INTERVAL = 0.1
MAX_ERRORS_LOGGED = 5
FLOAT_AT = struct.Struct("<f").unpack_from
POINTER_AT = struct.Struct("<Q").unpack_from

binder = native.Binder()
damage = meter.Meter()
listening: bool = False
listen_failed: bool = False
offsets: dict[str, int] = {}
flags: dict[str, tuple[int, int]] = {}
block_size: int = 0
# Damage type handle's bytes -> if it's damage over time
over_time_types: dict[bytes, bool] = {}
bound_pawn: WeakPointer = WeakPointer()
bound_address: int = 0
is_guest: bool = False
errors_logged: int = 0
fight_logged: meter.FightSummary | None = None
last_update: float = 0.0
last_bind_check: float = 0.0


def log_error_once(message: str) -> None:
    """Logs a problem, but not every frame."""
    global errors_logged  # noqa: PLW0603

    errors_logged += 1
    if errors_logged <= MAX_ERRORS_LOGGED:
        error(f"{LOG_TAG} {message}")


def set_up_listening() -> bool:
    """Reads where things are in the hit's details from the game, and checks it's all as expected."""
    global listening, listen_failed, block_size, offsets  # noqa: PLW0603

    if listening or listen_failed:
        return listening
    if not binder.ready():
        listen_failed = True
        return False
    try:
        offsets = native.struct_offsets()
        details = binder.func._find_prop("Details")
        for name in ("bWasCrit", "bIsDamageOverTime", "bCausedDeath"):
            prop = details.Struct._find_prop(name)
            flags[name] = (details.Offset_Internal + prop.Offset_Internal, int(getattr(prop, "FieldMask", 0xFF)) or 0xFF)
        sizes = {"damagedactor": 8, "damage": 4, "overkilldamage": 4, "damagetype": 8, "damageinstigator": 8, "attitudetowards": 1}
        end = max(offsets[name] + size for name, size in sizes.items())
        block_size = max(end, *(offset + 1 for offset, _ in flags.values()))
        if block_size > binder.func.ParamsSize:
            raise ValueError(f"fields end at {block_size}, past the {binder.func.ParamsSize} bytes of parameters")
    except Exception as ex:  # noqa: BLE001
        error(f"{LOG_TAG} The damage details changed shape: {ex!r}")
        listen_failed = True
        return False
    listening = True
    return True


def has_flag(raw: bytes, name: str) -> bool:
    """Reads one of the hit's yes or no fields."""
    offset, mask = flags[name]
    return bool(raw[offset] & mask)


def is_over_time(raw: bytes, args: WrappedStruct) -> bool:
    """Tells damage over time. The damage type's name says so too, and is only read once per type."""
    if has_flag(raw, "bIsDamageOverTime"):
        return True
    at = offsets["damagetype"]
    key = raw[at : at + 8]
    known = over_time_types.get(key)
    if known is None:
        try:
            known = str(args.Details.DamageType._name).lower().endswith("_status")
        except Exception:  # noqa: BLE001
            known = False
        over_time_types[key] = known
    return known


def record_hit(args: WrappedStruct) -> None:
    """Counts one hit. This runs for every one of them, so stays short, and mustn't break the game's damage."""
    try:
        raw = ctypes.string_at(args._get_address(), block_size)
        if raw[offsets["attitudetowards"]] != HOSTILE:
            return
        if not count_companions.value and POINTER_AT(raw, offsets["damageinstigator"])[0] != bound_address:
            return
        amount = FLOAT_AT(raw, offsets["damage"])[0]
        if not amount > 0:  # Also catches NaN
            return
        if not count_over_time.value and is_over_time(raw, args):
            return
        target = POINTER_AT(raw, offsets["damagedactor"])[0]
        damage.add(time.monotonic(), amount, has_flag(raw, "bWasCrit"), has_flag(raw, "bCausedDeath"), target)
    except Exception as ex:  # noqa: BLE001
        log_error_once(repr(ex))


@hook(native.FUNC_PATH, Type.PRE)
def on_caused_damage(obj: UObject, args: WrappedStruct, _ret: Any, _func: BoundFunction) -> Any:
    # Our binding calls this on the default object, anything else is the game's own use of it
    if obj._get_address() != binder.cdo_addr:
        return None
    if listening:
        record_hit(args)
    return Block


def check_binding(pc: UObject | None) -> None:
    """Keeps listening to the character you're playing, which is a new one after a respawn or a map change."""
    global bound_pawn, bound_address, is_guest  # noqa: PLW0603

    pawn = pc.Pawn if pc else None
    if not pawn or not set_up_listening():
        return
    try:
        role = pawn.Role
        is_guest = getattr(role, "value", role) != ROLE_AUTHORITY
    except AttributeError:
        is_guest = False
    address = pawn._get_address()
    if address != bound_address and binder.bind(pawn):
        bound_pawn = WeakPointer(pawn)
        bound_address = address
        info(f"{LOG_TAG} Listening to {pawn.Class.Name}, guest: {is_guest}")


def stop_listening() -> None:
    """Takes our entry back out of the character's list."""
    global bound_pawn, bound_address  # noqa: PLW0603

    pawn = bound_pawn()
    if pawn is not None:
        binder.unbind(pawn)
    bound_pawn = WeakPointer()
    bound_address = 0


# --- The window on screen -------------------------------------------------------------------------
WINDOW_NAME = "Bl4DpsMeter_Window"
WINDOW_Z_ORDER = 18
WIDGET_CHECK_INTERVAL = 1.0
DETAILS_FONT_RATIO = 0.65
GAME_FONT = "/Game/Fonts/Industry.Industry"
GAME_TYPEFACE = "Bold"
HIT_TEST_INVISIBLE = 3
ALIGN_FILL = 0  # EVerticalAlignment
ALIGN_CENTER = 2
SIZE_RULE_FILL = 1  # ESlateSizeRule
COLLAPSED = 1
SHADOW_COLOR = (0.0, 0.0, 0.0, 0.9)
SHADOW_OFFSET = 1.5
ONE_LINE_SEPARATOR = " | "


def linear(srgb: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    """Turns a colour as written on the web into the linear one UMG wants."""

    def channel(start: int) -> float:
        value = int(srgb[start : start + 2], 16) / 255.0
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    return (channel(1), channel(3), channel(5), alpha)


@dataclass(frozen=True)
class WindowStyle:
    """How the window looks."""

    background: tuple[float, float, float, float] | None
    accent: tuple[float, float, float, float] | None
    main: tuple[float, float, float, float]
    details: tuple[float, float, float, float]
    capitals: bool = False
    one_line: bool = False
    shadow: bool = False
    panel: bool = False  # Built like the game's own HUD panels


# The game's interface colours, as the Carnage Report takes them from its stylesheets
GAME_DARK = (0.0012, 0.0052, 0.0098, 0.88)
GAME_ORANGE = linear("#ff9b2e")
GAME_LIGHT_ORANGE = linear("#ffb55c")
GAME_TEXT = linear("#e4d9ce")
GAME_CYAN = linear("#00c6ff")
WHITE = linear("#ffffff")
# Picked from the health and ammo panels on the HUD
HUD_PANEL = linear("#0a324b", 0.82)
HUD_TILE = linear("#0f5a70", 0.92)
HUD_EDGE = linear("#aebfc8")
HUD_CYAN = linear("#39e3ea")
HUD_NUMBER = linear("#f0e8dc")
HUD_DETAILS = linear("#b4c8d2")
HUD_TICK_LENGTH = 18.0
HUD_LINE_WIDTH = 2.0
WINDOW_STYLES = {
    STYLE_GAME: WindowStyle(None, None, HUD_NUMBER, HUD_DETAILS, capitals=True, panel=True),
    STYLE_COMPACT: WindowStyle(GAME_DARK, None, GAME_LIGHT_ORANGE, GAME_TEXT, capitals=True, one_line=True),
    STYLE_MINIMAL: WindowStyle(None, None, WHITE, GAME_TEXT, shadow=True),
    STYLE_NEON: WindowStyle((0.0, 0.0, 0.0, 0.7), GAME_CYAN, GAME_CYAN, WHITE),
}

TEXT_TOTAL: Text = ("Razem", "Total")
TEXT_TIME: Text = ("Czas", "Time")
TEXT_CRITS: Text = ("Krytyki", "Crits")
TEXT_BEST: Text = ("Najlepsze", "Best")
TEXT_KILLS: Text = ("Zabójstwa", "Kills")
TEXT_LAST_FIGHT: Text = ("Ostatnia walka", "Last fight")
TEXT_GUEST: Text = ("Jako gość co-op gra nie podaje obrażeń", "As a co-op guest, the game doesn't report damage")
TEXT_NOT_LISTENING: Text = ("Patch gry: licznik czeka na aktualizację", "Game patched: the meter is waiting for an update")

window_widget: WeakPointer = WeakPointer()
window_owner: WeakPointer = WeakPointer()
window_layout: tuple[Any, ...] = ()
window_hidden: bool = False
main_label: UObject | None = None
details_label: UObject | None = None
main_shown: str = ""
details_shown: str = ""
last_widget_check: float = 0.0


def current_style() -> WindowStyle:
    """Gets the look that's been chosen."""
    return WINDOW_STYLES[window_style.key]


def main_text(now: float) -> str:
    """Gets the big line of the window."""
    number = meter.format_number(damage.dps(now))
    return number if current_style().panel else f"DPS {number}"


def details_text(now: float) -> str:
    """Gets the small lines of the window."""
    lines = []
    if listen_failed:
        lines.append(say(TEXT_NOT_LISTENING))
    elif is_guest:
        lines.append(say(TEXT_GUEST))
    if show_details.value:
        crit_share = 100.0 * damage.crit / damage.total if damage.total else 0.0
        lines.append(
            f"{say(TEXT_TOTAL)} {meter.format_number(damage.total)} | {say(TEXT_TIME)} {meter.format_time(damage.duration(now))}",
        )
        lines.append(
            f"{say(TEXT_CRITS)} {crit_share:.0f}% | {say(TEXT_BEST)} {meter.format_number(damage.biggest)}"
            f" | {say(TEXT_KILLS)} {damage.kills}",
        )
    last = damage.last_fight
    if show_last_fight.value and last is not None:
        lines.append(
            f"{say(TEXT_LAST_FIGHT)}: {meter.format_number(last.dps)} DPS"
            f" | {meter.format_number(last.total)} | {meter.format_time(last.duration)} | {say(TEXT_KILLS)} {last.kills}",
        )
    style = current_style()
    text = (ONE_LINE_SEPARATOR if style.one_line else "\n").join(lines)
    return text.upper() if style.capitals else text


def new_widget(path: str, outer: UObject) -> UObject:
    """Creates a new UMG object."""
    return construct_object(find_object("Class", path), outer)


def linear_color(rgba: tuple[float, float, float, float]) -> WrappedStruct:
    """Creates a linear colour struct."""
    return make_struct("LinearColor", R=rgba[0], G=rgba[1], B=rgba[2], A=rgba[3])


def set_game_font(text: UObject, size: int) -> None:
    """Uses the game's own font, if it's loaded. The default one is fine otherwise."""
    try:
        font = find_object("Font", GAME_FONT)
        text.SetFont(make_struct("SlateFontInfo", FontObject=font, TypefaceFontName=GAME_TYPEFACE, Size=size))
    except Exception:  # noqa: BLE001
        font_info = text.Font
        font_info.Size = size
        text.SetFont(font_info)


def new_text(tree: UObject, size: int, color: tuple[float, float, float, float], shadow: bool) -> UObject:
    """Creates a text block which never takes the mouse."""
    text = new_widget("/Script/UMG.TextBlock", tree)
    set_game_font(text, size)
    text.SetColorAndOpacity(make_struct("SlateColor", SpecifiedColor=linear_color(color)))
    if shadow:
        text.SetShadowColorAndOpacity(linear_color(SHADOW_COLOR))
        text.SetShadowOffset(make_struct("Vector2D", X=SHADOW_OFFSET, Y=SHADOW_OFFSET))
    text.SetVisibility(HIT_TEST_INVISIBLE)
    return text


def wanted_layout() -> tuple[Any, ...]:
    """Gets what the window gets built from, it needs building again if any of this changes."""
    return (window_style.key, *(float(option.value) for option in RELOAD_OPTIONS))


def new_line(tree: UObject, color: tuple[float, float, float, float], length: float = 1.0) -> UObject:
    """Creates a thin coloured line."""
    line = new_widget("/Script/UMG.Border", tree)
    line.SetBrushColor(linear_color(color))
    line.SetPadding(make_struct("Margin", Left=0.0, Top=0.0, Right=0.0, Bottom=0.0))
    spacer = new_widget("/Script/UMG.Spacer", tree)
    spacer.SetSize(make_struct("Vector2D", X=length, Y=HUD_LINE_WIDTH))
    line.SetContent(spacer)
    return line


def fill_width(widget: UObject) -> None:
    """Makes something in a horizontal box take up the space that's left."""
    widget.Slot.SetSize(make_struct("SlateChildSize", Value=1.0, SizeRule=SIZE_RULE_FILL))


def new_panel_edge(tree: UObject, tick_on_left: bool) -> UObject:
    """Creates the line along a panel's top or bottom, with its short orange end on the inner side."""
    edge = new_widget("/Script/UMG.HorizontalBox", tree)
    tick = new_line(tree, GAME_ORANGE, HUD_TICK_LENGTH)
    line = new_line(tree, HUD_EDGE)
    edge.AddChild(tick if tick_on_left else line)
    edge.AddChild(line if tick_on_left else tick)
    fill_width(line)
    return edge


def build_panel(tree: UObject, column: UObject, style: WindowStyle, on_right: bool) -> tuple[UObject, UObject]:
    """Lays the window out like the game's HUD panels. Returns its main and details texts."""
    column.AddChild(new_panel_edge(tree, on_right))

    row = new_widget("/Script/UMG.HorizontalBox", tree)
    column.AddChild(row)
    row.Slot.SetPadding(make_struct("Margin", Left=0.0, Top=3.0, Right=0.0, Bottom=3.0))

    details_size = max(8, int(font_size.value * DETAILS_FONT_RATIO))
    tile = new_widget("/Script/UMG.Border", tree)
    tile.SetBrushColor(linear_color(HUD_TILE))
    tile.SetPadding(make_struct("Margin", Left=10.0, Top=4.0, Right=10.0, Bottom=4.0))
    tile.SetVerticalAlignment(ALIGN_CENTER)
    title = new_text(tree, details_size, HUD_CYAN, style.shadow)
    title.SetText("DPS")
    tile.SetContent(title)
    row.AddChild(tile)
    tile.Slot.SetPadding(make_struct("Margin", Left=0.0, Top=0.0, Right=3.0, Bottom=0.0))
    tile.Slot.SetVerticalAlignment(ALIGN_FILL)

    values = new_widget("/Script/UMG.Border", tree)
    values.SetBrushColor(linear_color(HUD_PANEL))
    values.SetPadding(make_struct("Margin", Left=12.0, Top=2.0, Right=14.0, Bottom=5.0))
    row.AddChild(values)
    fill_width(values)
    stack = new_widget("/Script/UMG.VerticalBox", tree)
    values.SetContent(stack)
    main = new_text(tree, int(font_size.value), style.main, style.shadow)
    stack.AddChild(main)
    details = new_text(tree, details_size, style.details, style.shadow)
    stack.AddChild(details)

    column.AddChild(new_panel_edge(tree, on_right))
    return main, details


def build_window(pc: UObject) -> None:
    """Adds the window to the screen. It never takes the mouse or any input."""
    global window_widget, window_owner, window_layout, window_hidden  # noqa: PLW0603
    global main_label, details_label, main_shown, details_shown  # noqa: PLW0603

    # A fresh name each time, reusing one from a removed widget which hasn't been collected yet
    # would make Unreal recycle that object in place. The viewport keeps the widget alive.
    name = f"{WINDOW_NAME}_{time.monotonic_ns() % 10**12}"
    widget = construct_object(find_object("Class", "/Script/UMG.UserWidget"), pc, name)
    tree = new_widget("/Script/UMG.WidgetTree", widget)
    widget.WidgetTree = tree
    canvas = new_widget("/Script/UMG.CanvasPanel", tree)
    tree.RootWidget = canvas

    style = current_style()
    box = new_widget("/Script/UMG.Border", tree)
    box.SetBrushColor(linear_color(style.background or (0.0, 0.0, 0.0, 0.0)))
    padding = 0.0 if style.panel else 1.0
    box.SetPadding(make_struct("Margin", Left=12.0 * padding, Top=6.0 * padding, Right=12.0 * padding, Bottom=7.0 * padding))
    box.SetVisibility(HIT_TEST_INVISIBLE)
    canvas.AddChild(box)

    # Anchored by its own matching point, so it stays on screen wherever it's put
    place = make_struct("Vector2D", X=window_x.value / 100.0, Y=window_y.value / 100.0)
    slot = box.Slot
    slot.SetAnchors(make_struct("Anchors", Minimum=place, Maximum=place))
    slot.SetAlignment(place)
    slot.SetPosition(make_struct("Vector2D", X=0.0, Y=0.0))
    slot.SetAutoSize(True)

    column = new_widget("/Script/UMG.VerticalBox", tree)
    box.SetContent(column)

    if style.panel:
        main_label, details_label = build_panel(tree, column, style, window_x.value >= 50.0)  # noqa: PLR2004

    # A thin line along the top
    if style.accent is not None:
        accent = new_widget("/Script/UMG.Border", tree)
        accent.SetBrushColor(linear_color(style.accent))
        column.AddChild(accent)
        accent.Slot.SetPadding(make_struct("Margin", Bottom=5.0))
        spacer = new_widget("/Script/UMG.Spacer", tree)
        spacer.SetSize(make_struct("Vector2D", X=1.0, Y=2.0))
        accent.SetContent(spacer)

    if not style.panel:
        main_label = new_text(tree, int(font_size.value), style.main, style.shadow)
        column.AddChild(main_label)
        details_size = max(8, int(font_size.value * DETAILS_FONT_RATIO))
        details_label = new_text(tree, details_size, style.details, style.shadow)
        column.AddChild(details_label)
    main_shown = details_shown = ""

    widget.SetVisibility(HIT_TEST_INVISIBLE)
    widget.AddToViewport(WINDOW_Z_ORDER)
    window_widget = WeakPointer(widget)
    window_owner = WeakPointer(pc)
    window_layout = wanted_layout()
    window_hidden = False


def remove_window() -> None:
    """Takes the window off the screen, if it's there."""
    global window_widget, window_owner, main_label, details_label  # noqa: PLW0603

    widget = window_widget()
    window_widget = WeakPointer()
    window_owner = WeakPointer()
    main_label = details_label = None
    if widget is not None:
        widget.RemoveFromParent()


def update_window_text(now: float) -> None:
    """Changes what the window says, only touching the game if it's different."""
    global main_shown, details_shown  # noqa: PLW0603

    if main_label is None or details_label is None:
        return
    wanted_main = main_text(now)
    if wanted_main != main_shown:
        main_shown = wanted_main
        main_label.SetText(wanted_main)
    wanted_details = details_text(now)
    if wanted_details != details_shown:
        details_shown = wanted_details
        details_label.SetText(wanted_details)
        details_label.SetVisibility(HIT_TEST_INVISIBLE if wanted_details else COLLAPSED)


def check_window(pc: UObject | None) -> None:
    """Puts the window up, as the game clears what's on screen when changing maps. Not in the main menu."""
    if not show_window.value or pc is None or not pc.Pawn:
        remove_window()
        return
    widget = window_widget()
    if (
        widget is None
        or window_owner() is not pc
        or not widget.IsInViewport()
        or window_layout != wanted_layout()
    ):
        remove_window()
        build_window(pc)


def hide_window_in_menus(pc: UObject | None) -> None:
    """The game shows the mouse cursor while one of its menus is open, the window stays out of those."""
    global window_hidden  # noqa: PLW0603

    widget = window_widget()
    hidden = pc is not None and bool(pc.bShowMouseCursor)
    if widget is not None and hidden != window_hidden:
        widget.SetVisibility(COLLAPSED if hidden else HIT_TEST_INVISIBLE)
        window_hidden = hidden


def log_finished_fight() -> None:
    """Notes how a fight went in the log, once it's over."""
    global fight_logged  # noqa: PLW0603

    fight = damage.last_fight
    if fight is not fight_logged and fight is not None:
        fight_logged = fight
        info(f"{LOG_TAG} Fight over: {fight.dps:.0f} DPS, {fight.total:.0f} damage in {fight.duration:.1f} s")


def copy_settings_to_meter() -> None:
    """Gives the counting what's been chosen in the menus."""
    damage.mode = how_to_count.key
    damage.window = window_seconds.value
    damage.reset_after = reset_seconds.value if when_to_reset.key == RESET_AFTER_IDLE else None


# This runs every frame, Loot Magnet and BLImGui use the same hook as their game thread callback
@hook("/Script/Engine.CameraModifier:BlueprintModifyCamera", Type.POST_UNCONDITIONAL)
def on_tick(_obj: UObject, _args: WrappedStruct, _ret: Any, _func: BoundFunction) -> None:
    global last_update, last_bind_check, last_widget_check  # noqa: PLW0603

    now = time.monotonic()
    if now - last_update < UPDATE_INTERVAL:
        return
    last_update = now
    try:
        copy_settings_to_meter()
        damage.tick(now)
        log_finished_fight()
        if now - last_bind_check >= BIND_CHECK_INTERVAL:
            last_bind_check = now
            check_binding(get_pc())
        if now - last_widget_check >= WIDGET_CHECK_INTERVAL:
            last_widget_check = now
            check_window(get_pc())
        hide_window_in_menus(get_pc())
        update_window_text(now)
    except Exception as ex:  # noqa: BLE001
        log_error_once(repr(ex))


@keybind("Reset Meter", key="F6")
def reset_meter() -> None:
    damage.reset()
    info(f"{LOG_TAG} Reset")


def on_disable() -> None:
    stop_listening()
    remove_window()


label(
    reset_meter,
    ("Resetuj licznik", "Reset the meter"),
    ("Kończy walkę od razu. Przydatne przy liczeniu tylko ręcznie.", "Ends the fight straight away. Handy when only resetting by hand."),
)
COUNTING_OPTIONS = (how_to_count, window_seconds, when_to_reset, reset_seconds, count_over_time, count_companions)
CHOICES = (how_to_count, when_to_reset, window_style)
