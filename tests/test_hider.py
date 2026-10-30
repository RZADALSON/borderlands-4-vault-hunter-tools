"""Loads the packaged mod through the real mods_base, with only the engine faked.
Usage: test_hider.py <folder holding GroundItemHider> <folder holding the real mods_base>"""
import shutil, struct, sys, tempfile, types, zipfile
from pathlib import Path
from unittest.mock import MagicMock

root, mb_src = Path(sys.argv[1]), Path(sys.argv[2])

# --- Package exactly as the SDK loader expects: one root folder, named after the file ------------
dist = root / "GroundItemHider.sdkmod"
with zipfile.ZipFile(dist, "w", zipfile.ZIP_DEFLATED) as z:
    for f in ("__init__.py", "pyproject.toml"):
        z.write(root / "GroundItemHider" / f, f"GroundItemHider/{f}")
with zipfile.ZipFile(dist) as z:
    tops = {n.split("/")[0] for n in z.namelist()}
    assert tops == {dist.stem}, tops

# --- Real mods_base. The SDK runs py3.14, this machine has 3.12, so drop one 3.13-only default -----
tmp = Path(tempfile.mkdtemp(dir=Path(sys.argv[3])))
shutil.copytree(mb_src, tmp / "mods_base")
import re
for p in (tmp / "mods_base").glob("*.py"):
    src = p.read_text(encoding="utf8")
    src = re.sub(r"^(\s*(?:class|def) \w+\[[^\]=]+?) = [^\]]+\]", r"\1]", src, flags=re.M)
    src = re.sub(r"^(\s*except) ([\w.]+(?:, [\w.]+)+):", r"\1 (\2):", src, flags=re.M)
    p.write_text(src, encoding="utf8")
(tmp / "sdk_mods").mkdir()
shutil.copy(dist, tmp / "sdk_mods" / dist.name)

# --- Fake engine --------------------------------------------------------------------------------
world = {"InventoryPickup": [], "OakVendingMachine": []}
registered_hooks = []
sdk = types.ModuleType("unrealsdk")
sdk.__path__ = []
sdk.find_all = lambda name, exact=True: list(world[name])
sdk.find_object = sdk.find_class = sdk.construct_object = sdk.make_struct = MagicMock()
sdk.config = {}
sdk.__version_info__ = (3, 2, 0)
hooks = types.ModuleType("unrealsdk.hooks")
class Type:
    PRE, POST, POST_UNCONDITIONAL = 0, 1, 2
hooks.Type = Type
hooks.Block = type("Block", (), {})
hooks.add_hook = lambda path, typ, ident, fn: registered_hooks.append((path, typ, ident))
hooks.remove_hook = MagicMock(); hooks.log_all_calls = MagicMock()
hooks.prevent_hooking_direct_calls = MagicMock()
class Log:
    logs = []
    def __call__(self, m): Log.logs.append(m); print("  LOG:", m)
log = types.ModuleType("unrealsdk.logging")
for n in ("info", "warning", "error", "misc", "dev_warning"): setattr(log, n, Log())
log.Logger = MagicMock(); log.is_console_ready = lambda: False; log.set_console_level = MagicMock()
unreal = types.ModuleType("unrealsdk.unreal")
for n in ("BoundFunction", "UObject", "WrappedStruct", "UClass", "UFunction", "UScriptStruct", "WrappedArray", "WeakPointer", "UEnum", "UStruct", "UProperty", "ZProperty"):
    setattr(unreal, n, type(n, (), {}))
unreal.IGNORE_STRUCT = object()
cmds = types.ModuleType("unrealsdk.commands"); cmds.add_command = cmds.remove_command = cmds.has_command = MagicMock(); cmds.NEXT_LINE = 1
kb = MagicMock()
sys.modules["pyunrealsdk"] = MagicMock(__version__="pyunrealsdk 1.10.0")
sdk.__version__ = "unrealsdk 3.2.0"
import warnings
warnings.deprecated = lambda *a, **k: (lambda f: f)  # 3.13+
hooks.has_hook = lambda *a: False
for fake in (sdk, hooks, log, unreal, cmds):
    fake.__getattr__ = lambda name, _n=None: MagicMock() if not name.startswith("__") else (_ for _ in ()).throw(AttributeError(name))
sys.modules.update({"keybinds": kb, "keybinds.keybinds": kb, "unrealsdk": sdk, "unrealsdk.hooks": hooks, "unrealsdk.logging": log,
                    "unrealsdk.unreal": unreal, "unrealsdk.commands": cmds})

# --- Fake UMG ---------------------------------------------------------------------------------------
class W:
    made = []
    def __init__(self, cls, outer=None, name=None):
        self.cls, self.outer, self.name, self.calls, self.in_viewport = cls, outer, name, [], False
        self.Font = types.SimpleNamespace(Size=0); self.Slot = None; W.made.append(self)
    def AddChild(self, c): c.Slot = W("slot"); self.child = c
    def AddToViewport(self, z): self.in_viewport = True; self.z = z
    def RemoveFromParent(self): self.in_viewport = False
    def IsInViewport(self): return self.in_viewport
    def SetContent(self, c): self.content = c
    def __getattr__(self, name):
        if name.startswith("Set"):
            return lambda *a: self.calls.append((name, a))
        raise AttributeError(name)
class WP:
    def __init__(self, o=None): self.o = o
    def __call__(self): return self.o
unreal.WeakPointer = WP
THE_PC = types.SimpleNamespace(pc=1, Pawn=types.SimpleNamespace(K2_GetActorLocation=lambda: types.SimpleNamespace(X=0.0, Y=0.0, Z=0.0)), GetControlRotation=lambda: types.SimpleNamespace(Yaw=0.0))
sys.path[:0] = [str(tmp), str(tmp / "sdk_mods" / dist.name)]

import mods_base
mods_base.get_pc = lambda *a, **k: THE_PC
sdk.construct_object = lambda cls, outer=None, name=None: W(cls, outer, name)
sdk.find_object = lambda kind, path: path
sdk.make_struct = lambda n, **k: MagicMock() if n == "SlateBrush" else types.SimpleNamespace(struct=n, **k)
import GroundItemHider as m
assert ".sdkmod" in m.__file__, m.__file__

fails = 0
def check(label, got, want=True):
    global fails
    ok = got == want; fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {label}: {got}")

# --- The mod as the real mods_base built it --------------------------------------------------------
mod = mods_base.mod_list.mod_list[-1]
check("mod name", mod.name, "Ground Item Hider")
check("coop support", mod.coop_support.name, "ClientSide")
check("version", mod.version, "1.1")
check("hooks found", [h.hook_identifier and h.hook_funcs for h in mod.hooks][0][0][0], "/Script/Engine.CameraModifier:BlueprintModifyCamera")
check("keybinds", sorted(k.identifier for k in mod.keybinds), ["Print Loot Info", "Switch Filter Mode", "Toggle Item Hiding"])
check("toggle key", next(k.key for k in mod.keybinds if k.identifier == "Toggle Item Hiding"), "F8")
idents = {o.identifier for o in mod.options}
check("all options listed", {"Hide By Rarity", "Hide By Manufacturer", "Hide By Item Type", "Hide Pickups", "Protect Rarity And Above", "Filter Mode", "Highlight Filters"} <= idents)
check("11 manufacturers", len(m.manufacturer_options), 11)
check("11 gear types", len(m.gear_type_options), 11)

# --- Fake pickups -----------------------------------------------------------------------------------
CDO = object()
C = {v: k for k, v in reversed(m.BEAM_COLORS)}
class Beam:
    def __init__(self, color, **flags):
        names = {"User.Color": struct.pack("<4f", *color)}
        for k, v in flags.items(): names[f"User.{k}"] = struct.pack("<I", 0xFFFFFFFF if v else 0)
        data, offs = b"", []
        for n, v in names.items():
            offs.append(types.SimpleNamespace(Name=n, Offset=len(data))); data += v
        self.OverrideParameters = types.SimpleNamespace(ParameterData=data, SortedParameterOffsets=offs)
        self.hidden = False
    def SetHiddenInGame(self, h, propagate): self.hidden = h
    RelativeScale3D = types.SimpleNamespace(X=1.0, Y=1.0, Z=1.0)
    def _write(self, name, raw):
        store = self.OverrideParameters
        for p in store.SortedParameterOffsets:
            if p.Name == name and p.Offset >= 0:
                d = bytearray(store.ParameterData); d[p.Offset:p.Offset + len(raw)] = raw
                store.ParameterData = bytes(d); return
        store.SortedParameterOffsets.append(types.SimpleNamespace(Name=name, Offset=len(store.ParameterData)))
        store.ParameterData += raw
    def SetVariableLinearColor(self, name, c): self.writes = getattr(self, "writes", 0) + 1; self._write(name, struct.pack("<4f", c.R, c.G, c.B, c.A))
    def SetVariableBool(self, name, v): self._write(name, struct.pack("<I", 0xFFFFFFFF if v else 0))
    def SetRelativeScale3D(self, v): self.RelativeScale3D = v
class Root:
    def __init__(self, mat): self.mat = mat
    def GetNumMaterials(self): return 1 if self.mat else 0
    def GetMaterial(self, i): return types.SimpleNamespace(Name=self.mat)
class Item:
    n = 0
    Class = types.SimpleNamespace(ClassDefaultObject=CDO)
    def __init__(self, body="", mat="", beam=None):
        Item.n += 1; self.id = Item.n
        self.BodyData, self.AttractEffectComponent = body, beam
        self.RootPrimitiveComponent = Root(mat)
        self.bHidden = False
    def SetActorHiddenInGame(self, h): self.bHidden = h
    def IsActorBeingDestroyed(self): return False
    def K2_GetActorLocation(self): return self.location
    location = types.SimpleNamespace(X=0.0, Y=0.0, Z=0.0)
    def __str__(self): return f"InventoryPickup'/Level.InventoryPickup_{self.id}'"
def body(path): return f"InventoryBodyData'/Game/Gear/{path}'"
smg_jak = body("Weapons/SMG/JAK/Body_JAK_SM.Body_JAK_SM")
snip_vla = body("Weapons/Sniper/VLA/Body_VLA_SR.Body_VLA_SR")
pistol_ted = body("Weapons/Pistols/TED/Body_TED_PS.Body_TED_PS")
ar_ord = body("Weapons/AssaultRifles/ORD/Body_ORD_AR.Body_ORD_AR")
sg_mal = body("Weapons/Shotguns/MAL/Body_MAL_SG.Body_MAL_SG")
heavy_tor = body("Gadgets/HeavyWeapons/TOR/Body_TOR_HW.Body_TOR_HW")
shield_dad = body("Shields/_Shared/DAD/Body_DAD.Body_DAD")
grenade_bor = body("GrenadeGadgets/_Shared/x/Body_BOR_GRN_Inv.Body_BOR_GRN_Inv")
repkit = body("RepairKits/_Shared/Body_Repkit.Body_Repkit")
enh = body("Enhancements/_Shared/Body_Enh.Body_Enh")
cm = body("ClassMods/x/Body_Paladin_ClassMod.Body_Paladin_ClassMod")
def gear(b, r=m.EPIC, mat="MID_M_x", **f): return Item(b, mat, Beam(C[r], **f))

def reset():
    for group in (m.rarity_options, m.manufacturer_options, m.gear_type_options, m.pickup_options):
        for o in group.values(): o.value = False
    m.protected_rarity.value = m.RARITY_LABELS[m.LEGENDARY]
    m.hidden_by_us.clear()
def run(*items):
    world["InventoryPickup"] = list(items); m.apply_filter()
    return [i.bHidden for i in items]

# Defaults
for r, want in {m.COMMON: True, m.UNCOMMON: True, m.RARE: True, m.EPIC: False, m.LEGENDARY: False, m.PEARLESCENT: False}.items():
    i = gear(smg_jak, r); run(i)
    check(f"default {r}", i.bHidden, want)
    check(f"default {r} beam", i.AttractEffectComponent.hidden, want)

# Rarity bytes from the old table still classify the same
for raw, want in ((bytes((0xAB, 0xD1, 0x03, 0x3F, 0x1B, 0x67, 0xFB, 0x3E, 0xE8, 0xBB, 0x1F, 0x3F, 0, 0, 0x80, 0x3F)), m.COMMON),
                  (bytes((0xB9, 0x72, 0x9E, 0x3E, 0, 0, 0x80, 0x3F, 0xA4, 0xFC, 0x24, 0x3F, 0, 0, 0x80, 0x3F)), m.PEARLESCENT)):
    check(f"raw beam bytes {want}", m.classify_color(struct.unpack("<4f", raw)), want)

# Manufacturer
reset(); m.manufacturer_options["Jakobs"].value = True
a, b_, leg = gear(smg_jak), gear(snip_vla), gear(smg_jak, m.LEGENDARY)
check("jakobs hidden, vladof not, legendary jakobs protected", run(a, b_, leg), [True, False, False])
m.protected_rarity.value = m.NO_PROTECTION
check("protection off hides legendary jakobs", run(a, b_, leg), [True, False, True])
reset(); m.protected_rarity.value = m.RARITY_LABELS[m.EPIC]; m.manufacturer_options["Jakobs"].value = True
check("protect epic+", run(gear(smg_jak, m.EPIC), gear(smg_jak, m.RARE)), [False, True])

for path, code, name in ((pistol_ted, "TED", "Tediore"), (ar_ord, "ORD", "Order"), (sg_mal, "MAL", "Maliwan"), (heavy_tor, "TOR", "Torgue"),
                         (shield_dad, "DAD", "Daedalus"), (grenade_bor, "BOR", "Ripper"), (snip_vla, "VLA", "Vladof")):
    check(f"manufacturer {name}", m.get_manufacturer(path, ""), name)
for code, name in (("ATLAS", "Atlas"), ("COV", "COV"), ("HYP", "Hyperion")):
    check(f"enhancement material {name}", m.get_manufacturer(enh, f"MID_M_{code}_x"), name)
check("no manufacturer", m.get_manufacturer(repkit, "MID_M_LEG_x"), None)
reset(); m.manufacturer_options["Jakobs"].value = True
check("repkit by material", run(gear(repkit, mat="MID_M_JAK_x"), gear(repkit, mat="MID_M_TOR_x")), [True, False])
check("class mods ignore manufacturer", run(gear(cm, mat="MID_M_JAK_x")), [False])

# Item types
for path, name in ((smg_jak, m.SMG), (snip_vla, m.SNIPER), (pistol_ted, m.PISTOL), (ar_ord, m.ASSAULT_RIFLE), (sg_mal, m.SHOTGUN), (heavy_tor, m.HEAVY_WEAPON),
                   (shield_dad, m.SHIELD), (grenade_bor, m.GRENADE), (repkit, m.REPAIR_KIT), (enh, m.ENHANCEMENT), (cm, m.CLASS_MOD)):
    reset(); m.gear_type_options[name].value = True
    check(f"type {name}", run(gear(path), gear(smg_jak if path != smg_jak else snip_vla)), [True, False])
check("DLC path keeps its type", m.get_gear_type("X'/Game/DLC/Cello/Gear/Weapons/SMG/JAK/B.B'"), m.SMG)
reset(); m.gear_type_options[m.SMG].value = True
check("legendary smg protected", run(gear(smg_jak, m.LEGENDARY)), [False])

# Keep flags beat every filter
reset(); m.rarity_options[m.COMMON].value = True; m.gear_type_options[m.SMG].value = True
for flag in ("HasFirmware", "HasAnointment", "IsShiny"):
    check(f"keep {flag}", run(gear(smg_jak, m.COMMON, **{flag: True})), [False])
check("flag off doesn't keep", run(gear(smg_jak, m.COMMON, HasFirmware=False)), [True])
m.keep_firmware.value = False; check("keep disabled", run(gear(smg_jak, m.COMMON, HasFirmware=True)), [True]); m.keep_firmware.value = True

# Fail safe: unknown stays visible, with one warning per colour
reset(); m.gear_type_options[m.SMG].value = True; m.rarity_options[m.COMMON].value = True
Log.logs.clear()
check("unknown colour stays", run(Item(smg_jak, "MID", Beam((.1, .2, .3, 1.))), Item(smg_jak, "MID", Beam((.1, .2, .3, 1.)))), [False, False])
check("warned once", sum("Unknown beam" in l for l in Log.logs), 1)
check("gear with no beam stays", run(Item(smg_jak, "MID")), [False])
check("unknown gear type stays", run(gear(body("New/Thing.Thing"), m.RARE)), [False])
check("mission stays", run(Item("X'/Game/Missions/Y.Y'", "MI_Q", Beam(C[m.COMMON]))), [False])
check("mission colour stays", run(Item("", "x", Beam(C[m.MISSION]))), [False])

# Pickups
reset()
hp, am, cash = Item("X'/Game/Pickups/Health/H.H'", "MI_Health", Beam(C[m.HEALTH])), Item("", "MI_AMMO_SMG"), Item("", "x", Beam(C[m.MONEY]))
boost = Item("", "M_ShieldBooster_x")
check("pickups visible by default", run(hp, am, cash, boost), [False] * 4)
m.pickup_options[m.HEALTH].value = True; check("hide health", run(hp, am, cash, boost), [True, False, False, False])
m.pickup_options[m.AMMO].value = True; check("hide ammo (material only)", am.bHidden or run(hp, am, cash, boost)[1], True)
m.pickup_options[m.MONEY].value = True; check("hide money (beam only)", run(hp, am, cash, boost)[2], True)
m.pickup_options[m.SHIELD_BOOSTER].value = True; check("hide booster", run(hp, am, cash, boost)[3], True)
m.pickup_options[m.HEALTH].value = False; check("unhide health live", run(hp, am, cash, boost)[0], False)

# Lifecycle
reset(); m.rarity_options[m.COMMON].value = True
item = gear(smg_jak, m.COMMON); game_hidden = gear(smg_jak, m.COMMON); game_hidden.bHidden = True
iotd = gear(smg_jak, m.COMMON)
world["OakVendingMachine"] = [types.SimpleNamespace(Class=Item.Class, IsActorBeingDestroyed=lambda: False, GetIOTDForPlayer=lambda pc: iotd)]
run(item, game_hidden, iotd)
check("iotd untouched", iotd.bHidden, False)
check("not tracked when game hid it", str(game_hidden) in m.hidden_by_us, False)
m.toggle_hiding.callback(); check("F8 shows", item.bHidden, False); check("F8 leaves game's hidden", game_hidden.bHidden, True)
m.toggle_hiding.callback(); check("F8 hides again", item.bHidden, True)
m.on_disable(); check("disable restores", item.bHidden, False); check("not left paused", m.paused, False)
m.apply_filter(); world["InventoryPickup"].remove(item); m.apply_filter()
check("gone item forgotten", str(item) in m.hidden_by_us, False)
world["OakVendingMachine"] = []

# A dying object doesn't stop the rest
class Broken(Item):
    @property
    def bHidden(self): raise RuntimeError("dead object")
    @bHidden.setter
    def bHidden(self, v): pass
reset(); m.rarity_options[m.COMMON].value = True
ok_item = gear(smg_jak, m.COMMON); world["InventoryPickup"] = [Broken(smg_jak, "MID"), ok_item]; m.apply_filter()
check("broken item skipped", ok_item.bHidden, True)

# Tick throttling and the debug bind
calls = []; real = m.apply_filter; m.apply_filter = lambda: calls.append(1)
m.last_scan = 0.0; m.scan_interval.value = 1000.0
for _ in range(5): m.on_tick(None, None, None, None)
check("throttled to one scan", len(calls), 1); m.apply_filter = real; m.scan_interval.value = 1.0
world["InventoryPickup"] = [gear(smg_jak, m.COMMON), hp]; Log.logs.clear(); m.print_loot_info.callback()
check("debug bind prints", any("manufacturer=Jakobs" in l and "type=SMGs" in l for l in Log.logs))


# --- Second review --------------------------------------------------------------------------------
# A flag parameter with a negative offset isn't set, it must not protect the item
reset(); m.rarity_options[m.COMMON].value = True
neg = gear(smg_jak, m.COMMON)
neg.AttractEffectComponent.OverrideParameters.SortedParameterOffsets.append(types.SimpleNamespace(Name="User.HasFirmware", Offset=-1))
check("negative flag offset doesn't keep", run(neg), [True])
past = gear(smg_jak, m.COMMON)
past.AttractEffectComponent.OverrideParameters.SortedParameterOffsets.append(types.SimpleNamespace(Name="User.IsShiny", Offset=9999))
check("out of range flag doesn't keep", run(past), [True])
badc = Item(smg_jak, "MID", Beam(C[m.COMMON]))
badc.AttractEffectComponent.OverrideParameters.SortedParameterOffsets[0].Offset = -1
check("negative colour offset stays visible", run(badc), [False])

# Objects dying mid scan don't stop the rest
reset(); m.rarity_options[m.COMMON].value = True
dying = gear(smg_jak, m.COMMON); dying.IsActorBeingDestroyed = lambda: True
class Dead(Item):
    def IsActorBeingDestroyed(self): raise RuntimeError("dead")
good = gear(smg_jak, m.COMMON)
def bad_machine(pc): raise RuntimeError("dead machine")
world["OakVendingMachine"] = [types.SimpleNamespace(Class=Item.Class, IsActorBeingDestroyed=lambda: False, GetIOTDForPlayer=bad_machine)]
check("dying and dead skipped, good one filtered", run(dying, Dead(smg_jak, "MID"), good), [False, False, True])
world["OakVendingMachine"] = []

# The class default object is never touched
cdo = gear(smg_jak, m.COMMON); cdo.Class = types.SimpleNamespace(ClassDefaultObject=cdo)
check("CDO untouched", run(cdo), [False])

# The real enable/disable path of mods_base
reset(); m.rarity_options[m.COMMON].value = True
check("starts disabled on first install", mod.is_enabled, False)
registered_hooks.clear(); mod.enable()
check("enable registers the tick hook", [(p_, t) for p_, t, _ in registered_hooks], [("/Script/Engine.CameraModifier:BlueprintModifyCamera", Type.POST_UNCONDITIONAL)])
tick = gear(smg_jak, m.COMMON); world["InventoryPickup"] = [tick]; m.last_scan = 0.0
m.on_tick(None, None, None, None); check("tick hides", tick.bHidden, True)
mod.disable(); check("real disable restores", tick.bHidden, False)

# --- On screen warning ------------------------------------------------------------------------------
def widgets(): return [w for w in W.made if w.cls == "/Script/UMG.UserWidget"]
def live(): return [w for w in widgets() if w.in_viewport]
def tick_now(): m.last_scan = 0.0; m.on_tick(None, None, None, None)
reset(); world["InventoryPickup"] = []; m.paused = False; m.remove_banner(); W.made.clear()
tick_now()
check("banner shown once", len(live()), 1)
b = live()[0]
tree = b.WidgetTree; box = tree.RootWidget.child; text = box.content
check("name prefix", b.name.startswith("GroundItemHider_Banner_"))
check("owned by pc", b.outer is THE_PC)
sl = dict(box.Slot.calls)
check("anchored top right", (sl["SetAnchors"][0].Minimum.X, sl["SetAnchors"][0].Minimum.Y, sl["SetAnchors"][0].Maximum.X, sl["SetAnchors"][0].Maximum.Y), (1.0, 0.0, 1.0, 0.0))
check("aligned top right", (sl["SetAlignment"][0].X, sl["SetAlignment"][0].Y), (1.0, 0.0))
check("inside the screen", sl["SetPosition"][0].X < 0 and sl["SetPosition"][0].Y > 0)
check("auto sized", sl["SetAutoSize"], (True,))
check("text", dict(text.calls)["SetText"], ("FILTR AKTYWNY",))
check("font size", text.Font.Size, m.BANNER_FONT_SIZE)
check("never takes input", all(dict(w.calls)["SetVisibility"] == (3,) for w in (b, box, text)))
for _ in range(3): tick_now()
check("not rebuilt every scan", len(widgets()), 1)
b.in_viewport = False; tick_now()
check("rebuilt after map change", (len(widgets()), len(live())), (2, 1))
m.toggle_hiding.callback(); check("F8 removes it", len(live()), 0)
tick_now(); check("stays off while paused", len(live()), 0)
m.toggle_hiding.callback(); check("F8 brings it back", len(live()), 1)
other = types.SimpleNamespace(pc=2); m.update_banner(other)
check("new controller gets its own", (len(live()), live()[0].outer is other), (1, True))
m.update_banner(THE_PC)
real_build = m.build_banner
def boom(pc): raise RuntimeError("no umg")
m.build_banner = boom; m.remove_banner(); Log.logs.clear()
fil = gear(smg_jak, m.COMMON); m.rarity_options[m.COMMON].value = True; world["InventoryPickup"] = [fil]
tick_now(); tick_now()
check("filter still works if banner fails", fil.bHidden, True)
check("failure logged once", sum("on screen warning" in l for l in Log.logs), 1)
m.build_banner = real_build; m.banner_error_logged = False; world["InventoryPickup"] = []
mod.enable(); tick_now(); check("shown after enable", len(live()), 1)
mod.disable(); check("removed on disable", len(live()), 0)

# --- Highlight mode -----------------------------------------------------------------------------------
def fresh():
    reset()
    for group in (m.highlight_rarity_options, m.highlight_manufacturer_options, m.highlight_gear_type_options, m.highlight_pickup_options):
        for o in group.values(): o.value = False
    m.highlight_firmware.value = m.highlight_anointed.value = m.highlight_shiny.value = False
    m.boosted_beams.clear(); m.highlighted_items = []
    m.filter_mode.value = m.MODE_HIGHLIGHT; m.paused = False
    m.beam_intensity.value = 30.0; m.beam_size.value = 2.0; m.show_radar.value = True
    world["OakVendingMachine"] = []
def hl(*items):
    world["InventoryPickup"] = list(items); m.apply_filter()
    return [str(i) in m.boosted_beams for i in items]
def color_of(i): return m.read_beam_color(i.AttractEffectComponent)

check("mode defaults to hide", m.filter_mode.default_value, m.MODE_HIDE)
check("highlight defaults: legendary and pearl", sorted(k for k, o in m.highlight_rarity_options.items() if o.default_value), ["Legendary", "Pearlescent"])

fresh(); m.highlight_rarity_options[m.LEGENDARY].value = True
m.rarity_options[m.COMMON].value = True  # The hide filters don't apply in this mode
leg, com = gear(smg_jak, m.LEGENDARY), gear(smg_jak, m.COMMON)
check("only selected are boosted", hl(leg, com), [True, False])
check("nothing hidden in highlight mode", (leg.bHidden, com.bHidden, leg.AttractEffectComponent.hidden, com.AttractEffectComponent.hidden), (False,) * 4)
check("marker list", len(m.highlighted_items), 1)
want = C[m.LEGENDARY]
check("colour is 30x", all(abs(a - b * 30) < 0.01 for a, b in zip(color_of(leg)[:3], want[:3])))
check("alpha untouched", color_of(leg)[3], want[3])
check("legendary beam flag set", m.read_beam_flag(leg.AttractEffectComponent, m.BEAM_LEGENDARY_PARAM))
sc = leg.AttractEffectComponent.RelativeScale3D
check("scaled 2x", (sc.X, sc.Y, sc.Z), (2.0, 2.0, 2.0))
check("others not written", getattr(com.AttractEffectComponent, "writes", 0), 0)

# Doesn't confuse itself, or redo work
for _ in range(3): m.apply_filter()
check("no compounding", all(abs(a - b * 30) < 0.01 for a, b in zip(color_of(leg)[:3], want[:3])))
check("not rewritten each scan", leg.AttractEffectComponent.writes, 1)
check("still seen as legendary", m.get_beam_kind(leg.AttractEffectComponent, str(leg)), m.LEGENDARY)
Log.logs.clear(); m.apply_filter(); check("no unknown colour warnings", [l for l in Log.logs if "Unknown" in l], [])

# Changing the sliders, and the game resetting the beam
m.beam_intensity.value = 10.0; m.apply_filter()
check("brightness follows slider", all(abs(a - b * 10) < 0.01 for a, b in zip(color_of(leg)[:3], want[:3])))
m.beam_intensity.value = 30.0; m.apply_filter()
leg.AttractEffectComponent.SetVariableLinearColor("User.Color", types.SimpleNamespace(R=want[0], G=want[1], B=want[2], A=want[3]))
m.apply_filter()
check("reboosted after a game reset", all(abs(a - b * 30) < 0.01 for a, b in zip(color_of(leg)[:3], want[:3])))

# A reused actor is judged by what it is now
reuse = gear(smg_jak, m.LEGENDARY); hl(reuse)
reuse.AttractEffectComponent.SetVariableLinearColor("User.Color", types.SimpleNamespace(R=C[m.COMMON][0], G=C[m.COMMON][1], B=C[m.COMMON][2], A=1.0))
check("reused actor not highlighted", hl(reuse), [False])

# Restoring
fresh(); m.highlight_rarity_options[m.LEGENDARY].value = True
was = gear(smg_jak, m.LEGENDARY, IsLegendary=False); hl(was)
m.toggle_hiding.callback()
check("F8 restores colour", all(abs(a - b) < 1e-4 for a, b in zip(color_of(was), want)))
check("F8 restores flag", m.read_beam_flag(was.AttractEffectComponent, m.BEAM_LEGENDARY_PARAM), False)
check("F8 restores scale", was.AttractEffectComponent.RelativeScale3D.X, 1.0)
check("F8 clears markers", len(m.highlighted_items), 0)
m.toggle_hiding.callback(); check("F8 boosts again", str(was) in m.boosted_beams)
m.filter_mode.value = m.MODE_HIDE; m.apply_filter()
check("switching to hide restores", (str(was) in m.boosted_beams, was.AttractEffectComponent.RelativeScale3D.X), (False, 1.0))

# Hide mode unhides on the way to highlight
fresh(); m.filter_mode.value = m.MODE_HIDE; m.rarity_options[m.COMMON].value = True
h = gear(smg_jak, m.COMMON); run(h); check("hidden first", h.bHidden)
m.filter_mode.value = m.MODE_HIGHLIGHT; m.apply_filter(); check("everything drops in highlight mode", h.bHidden, False)

# What gets highlighted
fresh(); m.highlight_manufacturer_options["Jakobs"].value = True
check("by manufacturer", hl(gear(smg_jak), gear(snip_vla)), [True, False])
fresh(); m.highlight_gear_type_options[m.SNIPER].value = True
check("by type", hl(gear(smg_jak), gear(snip_vla)), [False, True])
fresh(); m.highlight_firmware.value = True
check("firmware flag", hl(gear(smg_jak, m.COMMON, HasFirmware=True), gear(smg_jak, m.COMMON, HasFirmware=False)), [True, False])
fresh(); m.highlight_rarity_options[m.COMMON].value = True
check("firmware off doesn't block rarity", hl(gear(smg_jak, m.COMMON, HasFirmware=True)), [True])
fresh(); m.highlight_gear_type_options[m.SMG].value = True
check("unknown colour left alone", hl(Item(smg_jak, "MID", Beam((.2, .3, .4, 1.)))), [False])
check("mission never", hl(Item("X'/Game/Missions/Y.Y'", "MI_Q", Beam(C[m.COMMON]))), [False])
fresh(); m.highlight_pickup_options[m.HEALTH].value = True
hb = Item("X'/Game/Pickups/Health/H.H'", "MI_Health", Beam(C[m.HEALTH])); nb = Item("", "M_Health_x")
check("pickup boosted", hl(hb), [True]); world["InventoryPickup"] = [hb, nb]; m.apply_filter()
check("pickup without beam still gets a marker", len(m.highlighted_items), 2)
fresh(); m.highlight_rarity_options[m.COMMON].value = True; iot = gear(smg_jak, m.COMMON)
world["OakVendingMachine"] = [types.SimpleNamespace(Class=Item.Class, IsActorBeingDestroyed=lambda: False, GetIOTDForPlayer=lambda pc: iot)]
check("item of the day left alone", hl(iot), [False]); world["OakVendingMachine"] = []

# A beam refusing the value is reported once
fresh(); m.highlight_rarity_options[m.COMMON].value = True; m.beam_error_logged = False; Log.logs.clear()
stub = gear(smg_jak, m.COMMON); stub.AttractEffectComponent.SetVariableLinearColor = lambda n, c: None
sb = gear(smg_jak, m.COMMON); sb.AttractEffectComponent.SetVariableLinearColor = lambda n, c: None
hl(stub, sb); check("refused colour warned once", sum("didn't take" in l for l in Log.logs), 1)

# A beam blowing up doesn't lose the marker pass for the rest
fresh(); m.highlight_rarity_options[m.COMMON].value = True
bad = gear(smg_jak, m.COMMON)
def explode(*a): raise RuntimeError("niagara gone")
bad.AttractEffectComponent.SetVariableBool = explode
fine = gear(smg_jak, m.COMMON); hl(bad, fine)
check("others highlighted past a failure", str(fine) in m.boosted_beams)

# --- Radar --------------------------------------------------------------------------------------------
def radars(): return [w for w in W.made if w.cls == "/Script/UMG.UserWidget" and (w.name or "").startswith("GroundItemHider_Radar")]
def live_radars(): return [w for w in radars() if w.in_viewport]
fresh(); m.remove_radar(); m.remove_banner(); W.made.clear(); world["InventoryPickup"] = []
tick_now(); check("radar in highlight mode", len(live_radars()), 1)
check("banner says highlight", dict([w for w in live() if w.name.startswith("GroundItemHider_Banner")][-1].WidgetTree.RootWidget.child.content.calls)["SetText"], ("FILTR AKTYWNY: PODSWIETLANIE",))
frame_slot = dict(live_radars()[0].WidgetTree.RootWidget.child.Slot.calls)
check("radar top right", (frame_slot["SetAnchors"][0].Minimum.X, frame_slot["SetAnchors"][0].Minimum.Y, frame_slot["SetAlignment"][0].X, frame_slot["SetAlignment"][0].Y), (1.0, 0.0, 1.0, 0.0))
check("radar under banner", frame_slot["SetPosition"][0].Y >= 70)
check("radar never takes input", dict(live_radars()[0].calls)["SetVisibility"], (3,))
check("pool size", len(m.radar_markers), m.RADAR_MAX_MARKERS)
for _ in range(3): tick_now()
check("radar not rebuilt", len(radars()), 1)

R = m.RADAR_SIZE / 2 - m.RADAR_MARKER_SIZE / 2
def near(a, b): return all(abs(x - y) < 0.01 for x, y in zip(a, b))
U = 100.0 * m.radar_range.value
check("ahead is up", near(m.radar_position(U / 2, 0, 0, U), (0, -R / 2)))
check("behind is down", near(m.radar_position(-U / 2, 0, 0, U), (0, R / 2)))
check("right is right", near(m.radar_position(0, U / 2, 0, U), (R / 2, 0)))
check("left is left", near(m.radar_position(0, -U / 2, 0, U), (-R / 2, 0)))
check("turning 90 right moves it left", near(m.radar_position(U / 2, 0, 90, U), (-R / 2, 0)))
check("far away stays on rim", near(m.radar_position(U * 10, 0, 0, U), (0, -R)))
check("same spot is the centre", near(m.radar_position(0, 0, 45, U), (0, 0)))

fresh(); m.highlight_rarity_options[m.LEGENDARY].value = True
a_ = gear(smg_jak, m.LEGENDARY); a_.location = types.SimpleNamespace(X=1000.0, Y=0.0, Z=0.0)
b_ = gear(smg_jak, m.LEGENDARY); b_.location = types.SimpleNamespace(X=0.0, Y=500.0, Z=0.0)
world["InventoryPickup"] = [a_, b_]; tick_now()
check("two markers shown", m.radar_markers_shown[:3], [True, True, False])
pos = dict(m.radar_markers[0].Slot.calls)
last = [c for c in m.radar_markers[0].Slot.calls if c[0] == "SetPosition"][-1][1][0]
check("nearest first", last.X > 0 and abs(last.Y) < 1)
check("marker visible", [c for c in m.radar_markers[0].calls if c[0] == "SetVisibility"][-1][1], (3,))
check("spare marker collapsed", [c for c in m.radar_markers[2].calls if c[0] == "SetVisibility"][-1][1], (1,))
world["InventoryPickup"] = [a_]; tick_now()
check("picked up item's marker goes", m.radar_markers_shown[:2], [True, False])

# Fast updates between scans, without another scan
m.last_scan = __import__("time").monotonic(); m.scan_interval.value = 1000.0; m.last_radar = 0.0
calls = []; real_af = m.apply_filter; m.apply_filter = lambda: calls.append(1)
before = len([c for c in m.radar_markers[0].Slot.calls if c[0] == "SetPosition"])
m.on_tick(None, None, None, None)
check("radar moves between scans", len([c for c in m.radar_markers[0].Slot.calls if c[0] == "SetPosition"]), before + 1)
check("without scanning", len(calls), 0); m.apply_filter = real_af; m.scan_interval.value = 1.0

# Lifecycle
live_radars()[0].in_viewport = False; tick_now(); check("radar back after map change", len(live_radars()), 1)
m.toggle_hiding.callback(); check("F8 removes radar", len(live_radars()), 0)
m.toggle_hiding.callback(); check("F8 returns radar", len(live_radars()), 1)
m.show_radar.value = False; tick_now(); check("radar can be turned off", len(live_radars()), 0)
check("beam stays with radar off", str(a_) in m.boosted_beams); m.show_radar.value = True; tick_now()
m.filter_mode.value = m.MODE_HIDE; tick_now(); check("no radar in hide mode", len(live_radars()), 0)
check("banner back to plain", dict([w for w in live() if w.name.startswith("GroundItemHider_Banner")][-1].WidgetTree.RootWidget.child.content.calls)["SetText"], ("FILTR AKTYWNY",))

# Radar failing doesn't stop the rest
fresh(); m.remove_radar(); m.radar_error_logged = False; Log.logs.clear()
real_br = m.build_radar; m.build_radar = explode; m.highlight_rarity_options[m.LEGENDARY].value = True
x_ = gear(smg_jak, m.LEGENDARY); world["InventoryPickup"] = [x_]; tick_now(); tick_now()
check("beam works if radar fails", str(x_) in m.boosted_beams); check("radar failure logged once", sum("radar" in l for l in Log.logs), 1)
m.build_radar = real_br; m.radar_error_logged = False

# The switch bind, the debug bind, and the real disable
fresh(); m.switch_filter_mode.callback(); check("switch to hide", m.filter_mode.value, m.MODE_HIDE)
m.switch_filter_mode.callback(); check("switch to highlight", m.filter_mode.value, m.MODE_HIGHLIGHT)
Log.logs.clear(); world["InventoryPickup"] = [x_]; m.print_loot_info.callback()
check("debug bind shows highlight", any("highlight=" in l and "beam_color=" in l for l in Log.logs))
x_ = gear(smg_jak, m.LEGENDARY); world["InventoryPickup"] = [x_]  # The last one had its record wiped by fresh()
mod.enable(); m.highlight_rarity_options[m.LEGENDARY].value = True; tick_now()
check("boosted before disable", str(x_) in m.boosted_beams)
mod.disable()
check("disable restores beam", (str(x_) in m.boosted_beams, x_.AttractEffectComponent.RelativeScale3D.X), (False, 1.0))
check("disable removes radar", len(live_radars()), 0)

# --- Menus ---------------------------------------------------------------------------------------------
check("polish option label", m.filter_mode.display_name, "Tryb filtra")
check("polish title follows", m.filter_mode.description_title, "Tryb filtra")
check("identifier kept for the settings file", m.filter_mode.identifier, "Filter Mode")
check("rarity label", m.rarity_options[m.RARE].display_name, "Rzadkie")
check("type label", m.gear_type_options[m.REPAIR_KIT].display_name, "Zestawy naprawcze")
check("pickup label", m.highlight_pickup_options[m.HEALTH].display_name, "Zdrowie")
check("manufacturer stays a name", m.manufacturer_options["Jakobs"].display_name, "Jakobs")
check("nothing left unlabelled", all(o.display_name != o.identifier or o in m.manufacturer_options.values() or o in m.highlight_manufacturer_options.values() for o in [*mod.options, *m.rarity_options.values(), *m.gear_type_options.values()]))
check("keybind label", next(k.display_name for k in mod.keybinds if k.identifier == "Toggle Item Hiding"), "Włącz lub wstrzymaj filtr")
m.filter_mode.value = "Hide"; m.protected_rarity.value = "Legendary"; m.fix_old_spinner_values()
check("old saved mode migrates", m.filter_mode.value, m.MODE_HIDE)
check("old saved protection migrates", m.protected_rarity.value, m.RARITY_LABELS[m.LEGENDARY])
check("protection still works", (m.is_protected(m.LEGENDARY), m.is_protected(m.EPIC)), (True, False))
m.protected_rarity.value = m.RARITY_LABELS[m.PEARLESCENT]; check("protect pearl only", (m.is_protected(m.PEARLESCENT), m.is_protected(m.LEGENDARY)), (True, False))
m.protected_rarity.value = m.NO_PROTECTION; check("no protection", m.is_protected(m.PEARLESCENT), False)

print("FAILS:", fails)
sys.exit(1 if fails else 0)
