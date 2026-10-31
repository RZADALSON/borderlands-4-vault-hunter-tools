"""Loads the packaged mod through the real mods_base, with only the engine faked.
Usage: test_dps.py <folder holding GroundItemHider> <folder holding the real mods_base> <scratch folder>"""
import ctypes, json, re, shutil, struct, sys, tempfile, time, types, warnings, zipfile
from pathlib import Path
from unittest.mock import MagicMock

root, mb_src = Path(sys.argv[1]), Path(sys.argv[2])

dist = root / "GroundItemHider.sdkmod"
with zipfile.ZipFile(dist, "w", zipfile.ZIP_DEFLATED) as z:
    for f in ("__init__.py", "dps.py", "localized.py", "meter.py", "native.py", "pyproject.toml"):
        z.write(root / "GroundItemHider" / f, f"GroundItemHider/{f}")
with zipfile.ZipFile(dist) as z:
    assert {n.split("/")[0] for n in z.namelist()} == {dist.stem}

# The SDK runs py3.14, this machine may have older
tmp = Path(tempfile.mkdtemp(dir=Path(sys.argv[3])))
shutil.copytree(mb_src, tmp / "mods_base")
for p in (tmp / "mods_base").glob("*.py"):
    src = p.read_text(encoding="utf8")
    src = re.sub(r"^(\s*(?:class|def) \w+\[[^\]=]+?) = [^\]]+\]", r"\1]", src, flags=re.M)
    src = re.sub(r"^(\s*except) ([\w.]+(?:, [\w.]+)+):", r"\1 (\2):", src, flags=re.M)
    p.write_text(src, encoding="utf8")
(tmp / "sdk_mods").mkdir()
shutil.copy(dist, tmp / "sdk_mods" / dist.name)

sdk = types.ModuleType("unrealsdk"); sdk.__path__ = []
sdk.config = {}; sdk.__version_info__ = (3, 2, 0); sdk.__version__ = "unrealsdk 3.2.0"
hooks = types.ModuleType("unrealsdk.hooks")
class Type: PRE, POST, POST_UNCONDITIONAL = 0, 1, 2
hooks.Type = Type; hooks.Block = type("Block", (), {})
hooks.add_hook = MagicMock(); hooks.remove_hook = MagicMock(); hooks.log_all_calls = MagicMock(); hooks.prevent_hooking_direct_calls = MagicMock(); hooks.has_hook = lambda *a: False
class Log:
    logs = []
    def __call__(self, m): Log.logs.append(m)
log = types.ModuleType("unrealsdk.logging")
for n in ("info", "warning", "error", "misc", "dev_warning"): setattr(log, n, Log())
log.Logger = MagicMock(); log.is_console_ready = lambda: False; log.set_console_level = MagicMock()
unreal = types.ModuleType("unrealsdk.unreal")
for n in ("BoundFunction", "UObject", "WrappedStruct", "UClass", "UFunction", "UScriptStruct", "WrappedArray", "UEnum", "UStruct", "UProperty", "ZProperty"):
    setattr(unreal, n, type(n, (), {}))
unreal.IGNORE_STRUCT = object()
cmds = types.ModuleType("unrealsdk.commands"); cmds.add_command = cmds.remove_command = cmds.has_command = MagicMock(); cmds.NEXT_LINE = 1
kb = MagicMock()
sys.modules["pyunrealsdk"] = MagicMock(__version__="pyunrealsdk 1.10.0")
warnings.deprecated = lambda *a, **k: (lambda f: f)
for fake in (sdk, hooks, log, unreal, cmds):
    fake.__getattr__ = lambda name, _n=None: MagicMock() if not name.startswith("__") else (_ for _ in ()).throw(AttributeError(name))
sys.modules.update({"keybinds": kb, "keybinds.keybinds": kb, "unrealsdk": sdk, "unrealsdk.hooks": hooks, "unrealsdk.logging": log, "unrealsdk.unreal": unreal, "unrealsdk.commands": cmds})

class W:
    made = []
    def __init__(self, cls, outer=None, name=None):
        self.cls, self.outer, self.name, self.calls, self.in_viewport = cls, outer, name, [], False
        self.Font = types.SimpleNamespace(Size=0); self.Slot = None; self.children = []; W.made.append(self)
    def AddChild(self, c): c.Slot = W("slot"); self.children.append(c)
    def AddToViewport(self, z): self.in_viewport = True; self.z = z
    def RemoveFromParent(self): self.in_viewport = False
    def IsInViewport(self): return self.in_viewport
    def SetContent(self, c): self.content = c
    def __getattr__(self, name):
        if name.startswith("Set"): return lambda *a: self.calls.append((name, a))
        raise AttributeError(name)
class WP:
    def __init__(self, o=None): self.o = o
    def __call__(self): return self.o
unreal.WeakPointer = WP
sys.path[:0] = [str(tmp), str(tmp / "sdk_mods" / dist.name)]

import mods_base
class Pawn:
    Class = types.SimpleNamespace(Name="OakCharacter")
    def __init__(self, address, role=3): self.address, self.Role = address, role
    def _get_address(self): return self.address
THE_PC = types.SimpleNamespace(Pawn=Pawn(0x5000), bShowMouseCursor=False)
mods_base.get_pc = lambda *a, **k: THE_PC
sdk.construct_object = lambda cls, outer=None, name=None: W(cls, outer, name)
sdk.find_object = lambda kind, path: path
sdk.make_struct = lambda n, **k: types.SimpleNamespace(struct=n, **k)
import GroundItemHider as app
m = app.dps
meter = m.meter
assert ".sdkmod" in m.__file__, m.__file__

fails = 0
def check(label, got, want=True):
    global fails
    ok = got == want; fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {label}: {got}")
def near(label, got, want):
    check(label, abs(got - want) < 1e-6, True) if abs(got - want) < 1e-6 else check(label, got, want)

mod = mods_base.mod_list.mod_list[-1]
check("name", mod.name, "Vault Hunter Tools"); check("version", mod.version, "2.0"); check("coop", mod.coop_support.name, "ClientSide")
check("reset key", "Reset Meter" in [k.identifier for k in mod.keybinds], True)
check("reset key", next(k.key for k in mod.keybinds if k.identifier == "Reset Meter"), "F6")
check("damage and both ticks hooked", sorted(h.hook_funcs[0][0] for h in mod.hooks), sorted([m.native.FUNC_PATH, "/Script/Engine.CameraModifier:BlueprintModifyCamera", "/Script/Engine.CameraModifier:BlueprintModifyCamera"]))
check("the two ticks don't clash", len({h.hook_identifier for h in mod.hooks}), len(list(mod.hooks)))

# --- Defaults: only resets after 5 seconds out of combat ------------------------------------------
check("counts the whole fight", m.how_to_count.key, meter.MODE_FIGHT); check("resets out of combat", m.when_to_reset.key, m.RESET_AFTER_IDLE); check("after 5 s", m.reset_seconds.value, 5.0)
check("dot on", m.count_over_time.value, True); check("companions on", m.count_companions.value, True)

# --- The counting --------------------------------------------------------------------------------
M = meter.Meter()
check("empty", (M.dps(0.0), M.duration(0.0)), (0.0, 0.0))
M.add(100.0, 500.0); near("one hit isn't a huge number", M.dps(100.0), 500.0)
M.add(102.0, 500.0, crit=True); M.add(104.0, 1000.0, kill=True)
near("over first to last hit", M.dps(104.0), 500.0); near("holds still while waiting", M.dps(108.9), 500.0)
check("totals", (M.total, M.crit, M.hits, M.kills, M.biggest), (2000.0, 500.0, 3, 1, 1000.0))
K = meter.Meter(); K.add(0.0, 1.0, kill=True, target=1); K.add(0.0, 1.0, kill=True, target=1); K.add(0.1, 1.0, kill=True, target=1); check("pellets on one enemy, one kill", K.kills, 1)
K.add(0.2, 1.0, kill=True, target=2); check("another enemy, another kill", K.kills, 2); K.add(0.3, 1.0, target=3); check("a hit that doesn't kill", K.kills, 2)
K.reset(); check("the last fight remembers its kills", (K.kills, K.last_fight.kills), (0, 2)); K.add(1.0, 1.0, kill=True, target=1); check("a new fight starts over", K.kills, 1)
M.tick(108.9); check("4.9 s out of combat: still going", M.hits, 3)
M.tick(109.0); check("5 s out of combat: starts over", M.hits, 0); check("nothing left", (M.total, M.dps(109.0)), (0.0, 0.0))
check("last fight kept", (M.last_fight.dps, M.last_fight.total, M.last_fight.duration), (500.0, 2000.0, 4.0))
M.add(200.0, 100.0); M.tick(204.0); M.add(204.0, 100.0); M.tick(208.9); check("a hit puts it off", M.hits, 2); M.tick(209.0); check("exactly 5 after the last", M.hits, 0)

M = meter.Meter(); M.reset_after = None; M.add(0.0, 100.0); M.tick(1e6); check("by hand: never by itself", M.hits, 1); M.reset(); check("until asked", (M.hits, M.last_fight.total), (0, 100.0))
M = meter.Meter(); M.reset(); check("resetting nothing keeps no fight", M.last_fight, None)
M.add(0.0, 10.0); M.reset(); M.reset(); check("a second reset keeps the last fight", M.last_fight.total, 10.0)



M = meter.Meter(); M.mode = meter.MODE_WINDOW; M.window = 5.0; M.add(0.0, 1000.0); near("window before it's full", M.dps(0.0), 1000.0)
M.add(2.0, 1000.0); near("window part full", M.dps(2.0), 1000.0); M.add(4.0, 1000.0)
near("window part full later", M.dps(4.0), 750.0); near("window full", M.dps(5.0), 600.0); near("old hits drop out", M.dps(6.0), 400.0); near("all drop out", M.dps(9.5), 0.0)
check("total stays whole", M.total, 3000.0); check("window summary covers the fight", (M.summary().dps, M.summary().duration), (750.0, 4.0))
M.window = 1.0; M.add(20.0, 5.0); M.add(21.5, 5.0); check("window doesn't pile up", len(M.recent), 1)

check("numbers", [meter.format_number(x) for x in (0, 999, 9999, 10000, 123456, 1234567, 1.5e9, 2e12)], ["0", "999", "9 999", "10.0K", "123.5K", "1.23M", "1.50B", "2.00T"])
check("times", [meter.format_time(x) for x in (0, 59.9, 60, 3599)], ["00:00", "00:59", "01:00", "59:59"])

# --- Hits from the game --------------------------------------------------------------------------
OFF = {"damagedactor": 0, "damage": 8, "overkilldamage": 12, "damagetype": 16, "damageinstigator": 24, "attitudetowards": 32}
m.offsets = OFF; m.flags.update({"bWasCrit": (33, 1), "bIsDamageOverTime": (33, 2), "bCausedDeath": (33, 4)}); m.block_size = 40
m.listening = True; m.binder.cdo_addr = 0xC0
real_add = m.damage
def hit(amount=100.0, over=0.0, instigator=0x5000, attitude=2, flags_byte=0, type_name="Fire", block=None, on=0xC0):
    raw = bytearray(40)
    struct.pack_into("<ffQQB", raw, 8, amount, over, 7 + hash(type_name) % 1000, instigator, attitude)
    raw[33] = flags_byte
    buf = ctypes.create_string_buffer(bytes(raw), 40)
    args = types.SimpleNamespace(_get_address=lambda: ctypes.addressof(buf), Details=types.SimpleNamespace(DamageType=types.SimpleNamespace(_name=type_name)))
    obj = types.SimpleNamespace(_get_address=lambda: on)
    fn = next(h for h in mod.hooks if h.hook_funcs[0][0] == m.native.FUNC_PATH)
    return fn(obj, args, None, None)
m.bound_address = 0x5000; m.damage.clear()
check("blocks our own call", hit(), hooks.Block); check("counted", m.damage.total, 100.0)
check("leaves the game's own calls", hit(on=0x999), None); check("not counted", m.damage.hits, 1)
m.damage.clear(); hit(attitude=1); check("friendly doesn't count", m.damage.hits, 0)
hit(amount=float("nan")); hit(amount=0.0); check("nothing to count", m.damage.hits, 0)
hit(amount=456686.0, over=456685.0); check("a dummy with no health left counts in full, as seen in game", m.damage.total, 456686.0)
m.damage.clear(); hit(flags_byte=1); hit(flags_byte=4); check("crit and kill", (m.damage.crit, m.damage.kills), (100.0, 1))
m.damage.clear(); m.count_over_time.value = False; hit(flags_byte=2); check("dot by flag left out", m.damage.hits, 0); hit(type_name="Fire_Status"); check("dot by name left out", m.damage.hits, 0); hit(type_name="Shock"); check("direct still counts", m.damage.hits, 1); m.count_over_time.value = True
hit(flags_byte=2); check("dot counts by default", m.damage.hits, 2)
m.damage.clear(); m.count_companions.value = False; hit(instigator=0x7777); check("companion left out", m.damage.hits, 0); hit(); check("own hit counts", m.damage.hits, 1); m.count_companions.value = True; hit(instigator=0x7777); check("companion counts by default", m.damage.hits, 2)
m.listening = False; m.damage.clear(); check("still blocks when not ready", hit(), hooks.Block); check("no count", m.damage.hits, 0); m.listening = True
broken = types.SimpleNamespace(_get_address=lambda: 0xC0); bad_args = types.SimpleNamespace(_get_address=lambda: (_ for _ in ()).throw(RuntimeError("boom")))
Log.logs.clear(); m.errors_logged = 0
for _ in range(9): m.on_caused_damage.__wrapped__(broken, bad_args, None, None) if hasattr(m.on_caused_damage, "__wrapped__") else m.record_hit(bad_args)
check("errors don't escape, and don't flood", sum("boom" in l for l in Log.logs), m.MAX_ERRORS_LOGGED)

# --- Listening to your character -----------------------------------------------------------------
class FakeBinder:
    def __init__(self): self.bound, self.unbound, self.ok = [], [], True
    def bind(self, pawn): self.bound.append(pawn.address); return self.ok
    def unbind(self, pawn): self.unbound.append(pawn.address); return True
    def ready(self): return True
    cdo_addr = 0xC0
fb = FakeBinder(); m.binder = fb; m.bound_address = 0; m.bound_pawn = WP()
m.check_binding(THE_PC); check("binds", fb.bound, [0x5000]); m.check_binding(THE_PC); check("only once", fb.bound, [0x5000])
THE_PC.Pawn = Pawn(0x6000); m.check_binding(THE_PC); check("a new character after a respawn", fb.bound, [0x5000, 0x6000]); check("hits follow it", m.bound_address, 0x6000)
THE_PC.Pawn = None; m.check_binding(THE_PC); check("no character, nothing happens", len(fb.bound), 2); check("keeps what it had", m.bound_address, 0x6000)
THE_PC.Pawn = Pawn(0x6000); fb.ok = False; m.bound_address = 0; m.check_binding(THE_PC); check("failed binding isn't remembered", m.bound_address, 0); m.check_binding(THE_PC); check("so it tries again", fb.bound[-2:], [0x6000, 0x6000]); fb.ok = True; m.check_binding(THE_PC)
check("host isn't a guest", m.is_guest, False); THE_PC.Pawn = Pawn(0x6000, role=types.SimpleNamespace(value=2)); m.check_binding(THE_PC); check("guest noticed, enum value", m.is_guest, True)
app.language_option.value = app.ENGLISH; check("guest told why", "CO-OP GUEST" in m.details_text(0.0), True); THE_PC.Pawn = Pawn(0x6000, role=3); m.check_binding(THE_PC); check("host again", m.is_guest, False)
no_role = types.SimpleNamespace(_get_address=lambda: 0x6000, Class=Pawn.Class); THE_PC.Pawn = no_role; m.check_binding(THE_PC); check("no role field isn't a guest", m.is_guest, False); THE_PC.Pawn = Pawn(0x6000)
m.stop_listening(); check("unbinds", fb.unbound, [0x6000]); check("forgets", m.bound_address, 0); m.stop_listening(); check("only once", fb.unbound, [0x6000])
m.check_binding(THE_PC)

# --- The window ----------------------------------------------------------------------------------
app.language_option.value = app.POLISH
W.made.clear(); m.remove_window(); m.check_window(THE_PC); widget = m.window_widget()
check("on screen", widget.in_viewport, True); check("owned by the player", m.window_owner(), THE_PC)
check("doesn't take input", ("SetVisibility", (m.HIT_TEST_INVISIBLE,)) in widget.calls, True)
place = next(w for w in W.made if w.cls == "slot" and any(c[0] == "SetAnchors" for c in w.calls))
anchors = dict(place.calls)["SetAnchors"][0]; check("default place, under the radar", (anchors.Minimum.X, anchors.Minimum.Y), (0.985, 0.26))
check("stays inside the screen", dict(place.calls)["SetAlignment"][0], anchors.Minimum)
count = len(W.made); m.check_window(THE_PC); check("not built twice", len(W.made), count)
m.damage.clear(); m.damage.last_fight = None; m.update_window_text(0.0)
said = lambda label: [c[1][0] for c in label.calls if c[0] == "SetText"]
check("main line", said(m.main_label)[-1], "0"); check("details", said(m.details_label)[-1], "RAZEM 0 | CZAS 00:00\nKRYTYKI 0% | NAJLEPSZE 0 | ZABÓJSTWA 0")
before = len(m.main_label.calls); m.update_window_text(0.0); check("no needless updates", len(m.main_label.calls), before)
m.damage.mode = meter.MODE_FIGHT; m.damage.add(0.0, 5000.0, crit=True, kill=True); m.damage.add(2.0, 15000.0); m.update_window_text(2.0)
check("numbers show", said(m.main_label)[-1], "10.0K"); check("details show", said(m.details_label)[-1], "RAZEM 20.0K | CZAS 00:02\nKRYTYKI 25% | NAJLEPSZE 15.0K | ZABÓJSTWA 1")
m.damage.reset(); m.update_window_text(3.0); check("after a reset", said(m.main_label)[-1], "0"); check("last fight stays", said(m.details_label)[-1].split("\n")[-1], "OSTATNIA WALKA: 10.0K DPS | 20.0K | 00:02 | ZABÓJSTWA 1")
app.language_option.value = app.ENGLISH; m.update_window_text(3.0); check("English", said(m.details_label)[-1].split("\n")[-1], "LAST FIGHT: 10.0K DPS | 20.0K | 00:02 | KILLS 1")
m.show_last_fight.value = False; m.update_window_text(3.0); check("last fight can go", "LAST FIGHT" in said(m.details_label)[-1], False); m.show_last_fight.value = True
m.show_details.value = False; m.show_last_fight.value = False; m.listen_failed = False; m.is_guest = False; m.update_window_text(3.0); check("details off, hidden", (said(m.details_label)[-1], dict(m.details_label.calls)["SetVisibility"]), ("", (m.COLLAPSED,)))
m.show_details.value = True; m.show_last_fight.value = True
m.listen_failed = True; check("says when a patch broke it", m.details_text(0.0).split("\n")[0], "GAME PATCHED: THE METER IS WAITING FOR AN UPDATE"); m.listen_failed = False
old = m.window_widget(); m.window_x.value = 80.0; m.check_window(THE_PC); check("moves when moved", (m.window_widget() is not old, old.in_viewport), (True, False)); m.window_x.value = m.window_x.default_value
old = m.window_widget(); m.check_window(THE_PC); old = m.window_widget(); m.font_size.value = 30; m.check_window(THE_PC); check("rebuilt for font size", m.window_widget() is not old, True); m.font_size.value = 20; m.check_window(THE_PC)
old = m.window_widget(); old.in_viewport = False; m.check_window(THE_PC); check("back after a map change", m.window_widget().in_viewport, True)
old = m.window_widget(); THE_PC2 = types.SimpleNamespace(Pawn=Pawn(1)); m.check_window(THE_PC2); check("new player controller, new window", m.window_owner(), THE_PC2); m.check_window(THE_PC)
m.show_window.value = False; m.check_window(THE_PC); check("can be turned off", m.window_widget(), None); m.update_window_text(0.0); m.show_window.value = True; m.check_window(THE_PC); check("and back on", m.window_widget().in_viewport, True)
m.check_window(None); check("no player, no window", m.window_widget(), None); menu_pc = types.SimpleNamespace(Pawn=None); m.check_window(THE_PC); m.check_window(menu_pc); check("not in the main menu", m.window_widget(), None); m.check_window(THE_PC)

# --- Styles --------------------------------------------------------------------------------------
check("looks like the game by default", m.window_style.key, m.STYLE_GAME)
check("every choice has a look", sorted(m.window_style.labels), sorted(m.WINDOW_STYLES))
near("colours turned linear, like the filter's text", m.GAME_TEXT[0], m.linear("#e4d9ce")[0]); check("matches the game's text colour", tuple(round(v, 2) for v in m.GAME_TEXT[:3]), (0.78, 0.69, 0.62))
check("black and white stay", (m.linear("#000000")[:3], m.linear("#ffffff")[:3]), ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)))
def build(style):
    m.window_style.value = style; W.made.clear(); m.check_window(THE_PC)
    colors = [c[1][0] for w in W.made for c in w.calls if c[0] == "SetBrushColor"]
    shadows = sum(c[0] == "SetShadowOffset" for w in W.made for c in w.calls)
    return types.SimpleNamespace(built=bool(W.made), colors=colors, shadows=shadows, main=dict(m.main_label.calls)["SetColorAndOpacity"][0].SpecifiedColor)
m.damage.clear(); m.damage.last_fight = None
got = build(m.STYLE_COMPACT); check("changing style rebuilds", got.built, True); check("compact has no line", len(got.colors), 1); check("compact on one line", m.details_text(0.0), "RAZEM 0 | CZAS 00:00 | KRYTYKI 0% | NAJLEPSZE 0 | ZABÓJSTWA 0" if app.shown_language == "pl" else "TOTAL 0 | TIME 00:00 | CRITS 0% | BEST 0 | KILLS 0")
got = build(m.STYLE_MINIMAL); check("text only has a clear background", got.colors[0].A, 0.0); check("and a shadow on both texts", got.shadows, 2); check("not in capitals", m.details_text(0.0).split(" ")[0] in ("Razem", "Total"), True)
got = build(m.STYLE_NEON); check("neon has a line", len(got.colors), 2); check("neon main colour", got.main.G, m.GAME_CYAN[1]); check("neon has no shadow", got.shadows, 0)
got = build(m.STYLE_GAME); check("game has orange ends", got.colors.count(next(c for c in got.colors if c.R == m.GAME_ORANGE[0])) >= 1, True); check("on the HUD's blue", any(c.A == m.HUD_PANEL[3] for c in got.colors), True); check("game has no shadow", got.shadows, 0)
check("no tilt", any(n == "SetRenderShear" for w in W.made for n, _ in w.calls), False)
W.made.clear(); m.check_window(THE_PC); check("same style, not rebuilt", W.made, [])
m.window_style.value = "Sam tekst"; check("style by its text", m.window_style.key, m.STYLE_MINIMAL); app.language_option.value = app.ENGLISH; check("reads in English", m.window_style.value, "Text only"); m.window_style.value = m.STYLE_GAME; check("default again", m.window_style.value, "Like the game")

# --- The frame hook, settings reaching the counting ------------------------------------------------
tick = m.on_tick
m.damage.clear(); m.damage.last_fight = None; m.how_to_count.value = meter.MODE_WINDOW; m.window_seconds.value = 9.0; m.last_update = 0.0; tick(None, None, None, None)
check("mode reaches it", (m.damage.mode, m.damage.window), (meter.MODE_WINDOW, 9.0)); m.how_to_count.value = meter.MODE_FIGHT; m.window_seconds.value = 5.0
m.when_to_reset.value = m.RESET_BY_HAND; m.last_update = 0.0; tick(None, None, None, None); check("by hand reaches it", m.damage.reset_after, None)
m.when_to_reset.value = m.RESET_AFTER_IDLE; m.reset_seconds.value = 7.0; m.last_update = 0.0; tick(None, None, None, None); check("seconds reach it", m.damage.reset_after, 7.0); m.reset_seconds.value = 5.0; m.last_update = 0.0; tick(None, None, None, None)
now = time.monotonic(); m.damage.add(now - 6.0, 100.0); m.last_update = 0.0; tick(None, None, None, None); check("the real thing resets out of combat", (m.damage.hits, m.damage.last_fight.total), (0, 100.0))
m.damage.add(now - 1.0, 100.0); m.last_update = 0.0; tick(None, None, None, None); check("not while fighting", m.damage.hits, 1)
m.last_update = time.monotonic(); calls = len(W.made); before = m.last_bind_check; tick(None, None, None, None); check("does nothing between updates", m.last_bind_check, before)
orig = m.check_binding; m.check_binding = lambda pc: (_ for _ in ()).throw(RuntimeError("frame boom")); Log.logs.clear(); m.errors_logged = 0; m.last_update = 0.0; m.last_bind_check = 0.0; tick(None, None, None, None); check("frame errors don't escape", any("frame boom" in l for l in Log.logs), True); m.check_binding = orig
m.reset_meter.callback(); check("the key resets", m.damage.hits, 0)
m.remove_window(); m.check_window(THE_PC); widget = m.window_widget(); widget.calls.clear(); m.hide_window_in_menus(THE_PC); check("no menu, nothing touched", widget.calls, [])
THE_PC.bShowMouseCursor = True; m.hide_window_in_menus(THE_PC); check("hidden in a menu", widget.calls[-1], ("SetVisibility", (m.COLLAPSED,))); count = len(widget.calls); m.hide_window_in_menus(THE_PC); check("only once", len(widget.calls), count)
m.window_x.value = 80.0; m.check_window(THE_PC); m.hide_window_in_menus(THE_PC); rebuilt = m.window_widget(); check("rebuilt in a menu, still hidden", rebuilt.calls[-1], ("SetVisibility", (m.COLLAPSED,))); m.window_x.value = m.window_x.default_value; m.check_window(THE_PC); widget = m.window_widget(); m.hide_window_in_menus(THE_PC)
THE_PC.bShowMouseCursor = False; m.hide_window_in_menus(THE_PC); check("back after the menu", widget.calls[-1], ("SetVisibility", (m.HIT_TEST_INVISIBLE,)))
m.hide_window_in_menus(None); check("no player, no crash", m.window_hidden, False)
for language, name in ((app.ENGLISH, "Whole fight"),):
    app.language_option.value = language; check("default has a real name", m.how_to_count.default_value, name); m.how_to_count.value = m.how_to_count.default_value; check("default reads as unchanged", m.how_to_count.value == m.how_to_count.default_value, True); check("and is the right one", m.how_to_count.key, "fight")
m.on_disable(); check("disable cleans up", (m.window_widget(), m.bound_address), (None, 0))

# --- Language ------------------------------------------------------------------------------------
def walk(options):
    for option in options:
        yield option
        yield from walk(getattr(option, "children", ()))
app.set_game_language(app.POLISH); app.language_option.value = app.LANGUAGE_AUTO; check("follows the game", (app.shown_language, m.how_to_count.value, m.how_to_count.display_name), ("pl", "Cała walka", "Liczenie DPS"))
app.set_game_language(app.ENGLISH); app.apply_language(); check("in English", (app.shown_language, m.how_to_count.value, m.how_to_count.display_name), ("en", "Whole fight", "DPS calculation"))
app.set_game_language(app.POLISH); app.language_option.value = app.ENGLISH; check("a choice wins", app.shown_language, "en")
letters = set("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ"); left = [o.display_name for o in [*walk(mod.options), *mod.keybinds] if letters & set(o.display_name + (o.description or "")) and o is not app.language_option]; check("no Polish left in English", left, [])
m.how_to_count.value = meter.MODE_WINDOW; app.language_option.value = app.POLISH; check("choice survives the language", (m.how_to_count.key, m.how_to_count.value), (meter.MODE_WINDOW, "Ostatnie sekundy"))
m.how_to_count.value = "Last few seconds"; check("text in the other language", m.how_to_count.key, meter.MODE_WINDOW)

# --- Settings, through the real code and a real file -----------------------------------------------
app.language_option.value = app.ENGLISH; m.how_to_count.value = meter.MODE_WINDOW; m.when_to_reset.value = m.RESET_BY_HAND; m.reset_seconds.value = 12.0; mod.save_settings()
disk = json.loads(Path(mod.settings_file).read_text(encoding="utf8"))
def saved(tree, name):
    if name in tree: return tree[name]
    return next((v for v in (saved(c, name) for c in tree.values() if isinstance(c, dict)) if v is not None), None)
check("saved by meaning", (saved(disk, "Language"), saved(disk, "How To Count"), saved(disk, "When To Reset")), (app.ENGLISH, meter.MODE_WINDOW, m.RESET_BY_HAND))
app.language_option.value = app.POLISH; m.how_to_count.value = meter.MODE_FIGHT; m.when_to_reset.value = m.RESET_AFTER_IDLE; m.reset_seconds.value = 5.0; mod.load_settings()
check("loaded back", (app.language_option.key, app.shown_language, m.how_to_count.key, m.how_to_count.value, m.when_to_reset.key, m.reset_seconds.value), (app.ENGLISH, "en", meter.MODE_WINDOW, "Last few seconds", m.RESET_BY_HAND, 12.0))
m.how_to_count._from_json("rubbish"); check("nonsense changes nothing", m.how_to_count.key, meter.MODE_WINDOW)
m.how_to_count._from_json("clock"); check("a removed way of counting changes nothing", m.how_to_count.key, meter.MODE_WINDOW); m.how_to_count._from_json("active"); check("nor the other one", m.how_to_count.key, meter.MODE_WINDOW)
m.how_to_count.value = meter.MODE_FIGHT; check("seconds grey with the whole fight", m.window_seconds.greyed_when(), True); m.how_to_count.value = meter.MODE_WINDOW; check("not with the last seconds", m.window_seconds.greyed_when(), False); m.how_to_count.value = meter.MODE_FIGHT
m.when_to_reset.value = m.RESET_BY_HAND; check("reset time grey by hand", m.reset_seconds.greyed_when(), True); m.when_to_reset.value = m.RESET_AFTER_IDLE; check("not when automatic", m.reset_seconds.greyed_when(), False)
m.show_window.value = False; check("window settings grey when hidden", all(o.greyed_when() for o in m.WINDOW_OPTIONS), True); m.show_window.value = True; check("and back", any(o.greyed_when() for o in m.WINDOW_OPTIONS), False); check("the switch itself never greys", hasattr(m.show_window, "greyed_when"), False)

shutil.rmtree(tmp, ignore_errors=True)
print("FAILS:", fails)
sys.exit(1 if fails else 0)
