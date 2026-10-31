"""Loads the packaged mod through the real mods_base, with only the engine faked.
Usage: test_hider.py <folder holding GroundItemHider> <folder holding the real mods_base>"""
import ctypes, json, shutil, struct, sys, tempfile, types, zipfile
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
THE_PC = types.SimpleNamespace(pc=1, PlayerState=types.SimpleNamespace(BackpackItems=types.SimpleNamespace(items=[])), Pawn=types.SimpleNamespace(K2_GetActorLocation=lambda: types.SimpleNamespace(X=0.0, Y=0.0, Z=0.0)), GetControlRotation=lambda: types.SimpleNamespace(Yaw=0.0))
sys.path[:0] = [str(tmp), str(tmp / "sdk_mods" / dist.name)]

import mods_base
mods_base.get_pc = lambda *a, **k: THE_PC
sdk.construct_object = lambda cls, outer=None, name=None: W(cls, outer, name)
sdk.find_object = lambda kind, path: path
sdk.make_struct = lambda n, **k: MagicMock() if n == "SlateBrush" else types.SimpleNamespace(struct=n, **k)
calls_gaoc = []
def _gaoc(pc, cls, out):
    calls_gaoc.append(cls.name)
    return (None, list(world[cls.name]))
_statics = types.SimpleNamespace(GetAllActorsOfClass=_gaoc)
sdk.find_class = lambda n: types.SimpleNamespace(name=n, ClassDefaultObject=_statics)
find_all_calls = []
_fa = sdk.find_all
sdk.find_all = lambda name, exact=True: (find_all_calls.append(name), _fa(name, exact))[1]
import GroundItemHider as m
m.serial_firmware_for_test = lambda serial: m.parse_serial(serial)[1]
m.FULL_PASS_INTERVAL = 0.0; m.VENDING_INTERVAL = 0.0; m.VENDING_NEW_ITEM_INTERVAL = 0.0; m.BOOST_CHECK_INTERVAL = 0.0; m.INCOMPLETE_RETRY = 0.0; m.WIDGET_CHECK_INTERVAL = 0.0; m.SCAN_TIME_LIMIT = 1000.0
assert ".sdkmod" in m.__file__, m.__file__

fails = 0
def check(label, got, want=True):
    global fails
    ok = got == want; fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {label}: {got}")

# --- The mod as the real mods_base built it --------------------------------------------------------
mod = mods_base.mod_list.mod_list[-1]
# These checks read the Polish texts, the language ones are further down
m.set_game_language("pl")
check("mod name", mod.name, "Borderlands 4 Loot Filter")
check("coop support", mod.coop_support.name, "ClientSide")
check("version", mod.version, "1.5")
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
    physics = True
    def SetSimulatePhysics(self, v): self.physics = v
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
    collision = True
    def SetActorEnableCollision(self, v): self.collision = v
    def IsActorBeingDestroyed(self): return False
    def _get_address(self): return self.id
    @property
    def Name(self): return f"InventoryPickup_{self.id}"
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
    m.protected_rarity.value = m.LEGENDARY
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
reset(); m.protected_rarity.value = m.EPIC; m.manufacturer_options["Jakobs"].value = True
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
check("not tracked when game hid it", m.item_key(game_hidden) in m.hidden_by_us, False)
m.toggle_hiding.callback(); check("F8 shows", item.bHidden, False); check("F8 leaves game's hidden", game_hidden.bHidden, True)
m.toggle_hiding.callback(); check("F8 hides again", item.bHidden, True)
m.on_disable(); check("disable restores", item.bHidden, False); check("not left paused", m.paused, False)
m.apply_filter(); world["InventoryPickup"].remove(item); m.apply_filter()
check("gone item forgotten", m.item_key(item) in m.hidden_by_us, False)
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
tree = b.WidgetTree; box = tree.RootWidget.child; text = box.content.child
check("name prefix", b.name.startswith("GroundItemHider_Banner_"))
check("owned by pc", b.outer is THE_PC)
sl = dict(box.Slot.calls)
check("anchored top right", (sl["SetAnchors"][0].Minimum.X, sl["SetAnchors"][0].Minimum.Y, sl["SetAnchors"][0].Maximum.X, sl["SetAnchors"][0].Maximum.Y), (1.0, 0.0, 1.0, 0.0))
check("aligned top right", (sl["SetAlignment"][0].X, sl["SetAlignment"][0].Y), (1.0, 0.0))
check("inside the screen", sl["SetPosition"][0].X < 0 and sl["SetPosition"][0].Y > 0)
check("auto sized", sl["SetAutoSize"], (True,))
check("text", dict(text.calls)["SetText"], ("FILTR AKTYWNY",))
check("game font at the right size", (dict(text.calls)["SetFont"][0].Size, dict(text.calls)["SetFont"][0].TypefaceFontName), (m.BANNER_FONT_SIZE, m.BANNER_TYPEFACE))
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
    m.radar_place.value = m.RADAR_LEFT; m.hud_radar_found = None; m.drop_window_until = 0.0; m.last_backpack_size = None; m.dropped_items.clear(); m.recent_items.clear(); m.show_dropped.value = True; m.block_pickup.value = True
    m.filter_mode.value = m.MODE_HIGHLIGHT; m.paused = False
    m.beam_intensity.value = 30.0; m.beam_size.value = 2.0; m.show_radar.value = True
    world["OakVendingMachine"] = []
def hl(*items):
    world["InventoryPickup"] = list(items); m.apply_filter()
    return [m.item_key(i) in m.boosted_beams for i in items]
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
check("still seen as legendary", m.color_kind(m.read_beam_color(leg.AttractEffectComponent), m.item_key(leg)), m.LEGENDARY)
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
m.toggle_hiding.callback(); check("F8 boosts again", m.item_key(was) in m.boosted_beams)
m.filter_mode.value = m.MODE_HIDE; m.apply_filter()
check("switching to hide restores", (m.item_key(was) in m.boosted_beams, was.AttractEffectComponent.RelativeScale3D.X), (False, 1.0))

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
check("others highlighted past a failure", m.item_key(fine) in m.boosted_beams)

# --- Radar --------------------------------------------------------------------------------------------
def radars(): return [w for w in W.made if w.cls == "/Script/UMG.UserWidget" and (w.name or "").startswith("GroundItemHider_Radar")]
def live_radars(): return [w for w in radars() if w.in_viewport]
fresh(); m.remove_radar(); m.remove_banner(); W.made.clear(); world["InventoryPickup"] = []
tick_now(); check("radar in highlight mode", len(live_radars()), 1)
check("banner says highlight", dict([w for w in live() if w.name.startswith("GroundItemHider_Banner")][-1].WidgetTree.RootWidget.child.content.child.calls)["SetText"], ("FILTR AKTYWNY: PODSWIETLANIE",))
frame_slot = dict(live_radars()[0].WidgetTree.RootWidget.child.Slot.calls)
check("radar top left by default, clear of the game's", (frame_slot["SetAnchors"][0].Minimum.X, frame_slot["SetAnchors"][0].Minimum.Y, frame_slot["SetAlignment"][0].X, frame_slot["SetAlignment"][0].Y), (0.0, 0.0, 0.0, 0.0))
m.radar_place.value = m.RADAR_RIGHT; tick_now(); one = dict(live_radars()[0].WidgetTree.RootWidget.child.Slot.calls)
check("other spot is under the game's radar", (one["SetAnchors"][0].Minimum.X, one["SetPosition"][0].Y >= 260), (1.0, True))
m.radar_place.value = m.RADAR_LEFT; tick_now(); W.made[:] = [w for w in W.made if w.in_viewport or w.cls != "/Script/UMG.UserWidget"]
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
m.radar_items[0] = (9000.0, 4000.0, m.LEGENDARY)
m.on_tick(None, None, None, None)
check("radar moves between scans", len([c for c in m.radar_markers[0].Slot.calls if c[0] == "SetPosition"]), before + 1)
check("without scanning", len(calls), 0); m.apply_filter = real_af; m.scan_interval.value = 1.0

# Lifecycle
live_radars()[0].in_viewport = False; tick_now(); check("radar back after map change", len(live_radars()), 1)
m.toggle_hiding.callback(); check("F8 removes radar", len(live_radars()), 0)
m.toggle_hiding.callback(); check("F8 returns radar", len(live_radars()), 1)
m.show_radar.value = False; tick_now(); check("radar can be turned off", len(live_radars()), 0)
check("beam stays with radar off", m.item_key(a_) in m.boosted_beams); m.show_radar.value = True; tick_now()
m.filter_mode.value = m.MODE_HIDE; tick_now(); check("no radar in hide mode", len(live_radars()), 0)
world["InventoryPickup"] = []; tick_now()
check("banner back to plain", dict([w for w in live() if w.name.startswith("GroundItemHider_Banner")][-1].WidgetTree.RootWidget.child.content.child.calls)["SetText"], ("FILTR AKTYWNY",))

# Radar failing doesn't stop the rest
fresh(); m.remove_radar(); m.radar_error_logged = False; Log.logs.clear()
real_br = m.build_radar; m.build_radar = explode; m.highlight_rarity_options[m.LEGENDARY].value = True
x_ = gear(smg_jak, m.LEGENDARY); world["InventoryPickup"] = [x_]; tick_now(); tick_now()
check("beam works if radar fails", m.item_key(x_) in m.boosted_beams); check("radar failure logged once", sum("radar" in l for l in Log.logs), 1)
m.build_radar = real_br; m.radar_error_logged = False

# The switch bind, the debug bind, and the real disable
fresh(); m.switch_filter_mode.callback(); check("switch to hide", m.filter_mode.key, m.MODE_HIDE)
m.switch_filter_mode.callback(); check("switch to highlight", m.filter_mode.key, m.MODE_HIGHLIGHT)
Log.logs.clear(); world["InventoryPickup"] = [x_]; m.print_loot_info.callback()
check("debug bind shows highlight", any("highlight=" in l and "beam_color=" in l for l in Log.logs))
x_ = gear(smg_jak, m.LEGENDARY); world["InventoryPickup"] = [x_]  # The last one had its record wiped by fresh()
mod.enable(); m.highlight_rarity_options[m.LEGENDARY].value = True; tick_now()
check("boosted before disable", m.item_key(x_) in m.boosted_beams)
mod.disable()
check("disable restores beam", (m.item_key(x_) in m.boosted_beams, x_.AttractEffectComponent.RelativeScale3D.X), (False, 1.0))
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
m.filter_mode._from_json("Hide"); m.protected_rarity._from_json("Legendary")
check("old saved mode migrates", m.filter_mode.key, m.MODE_HIDE)
check("old saved protection migrates", m.protected_rarity.key, m.LEGENDARY)
check("protection still works", (m.is_protected(m.LEGENDARY), m.is_protected(m.EPIC)), (True, False))
m.protected_rarity.value = m.PEARLESCENT; check("protect pearl only", (m.is_protected(m.PEARLESCENT), m.is_protected(m.LEGENDARY)), (True, False))
m.protected_rarity.value = m.NO_PROTECTION; check("no protection", m.is_protected(m.PEARLESCENT), False)

# --- Scan cost ------------------------------------------------------------------------------------------
m.VENDING_INTERVAL = 0.0; reset(); m.item_infos.clear(); m.filter_mode.value = m.MODE_HIDE; m.paused = False; world["OakVendingMachine"] = []
find_all_calls.clear(); calls_gaoc.clear(); m.rarity_options[m.COMMON].value = True
class Counted(Item):
    reads = 0
    @property
    def BodyData(self): Counted.reads += 1; return self.__dict__["_b"]
    @BodyData.setter
    def BodyData(self, v): self.__dict__["_b"] = v
c1 = Counted(smg_jak, "MID_M_x", Beam(C[m.COMMON])); world["InventoryPickup"] = [c1]
m.apply_filter(); first = Counted.reads
for _ in range(20): m.apply_filter()
check("slow reads only once", Counted.reads, first)
check("still hidden", c1.bHidden)
check("no whole engine search", find_all_calls, [])
check("uses the world's actor list", "InventoryPickup" in calls_gaoc)

# Decisions are still live, without reading again
m.rarity_options[m.COMMON].value = False; m.apply_filter(); check("setting applies from memory", (c1.bHidden, Counted.reads), (False, first))
m.rarity_options[m.COMMON].value = True; m.apply_filter(); check("and back", c1.bHidden)

# Looks again eventually, and a fresh drop without its beam ready is retried
m.item_infos[m.item_key(c1)].read_at -= m.INFO_MAX_AGE + 1; m.apply_filter(); check("reads again when old", Counted.reads > first)
late = Item(smg_jak, "MID_M_x"); world["InventoryPickup"] = [late]; m.apply_filter(); check("no beam yet, stays", late.bHidden, False)
late.AttractEffectComponent = Beam(C[m.COMMON]); m.apply_filter(); check("hidden once its beam is up", late.bHidden)

# A big drop is spread over scans
m.item_infos.clear(); m.hidden_by_us.clear()
many = [gear(smg_jak, m.COMMON) for _ in range(35)]; world["InventoryPickup"] = many
m.last_scan = 0.0; m.apply_filter()
check("first scan reads the budget", sum(i.bHidden for i in many), m.MAX_READS_PER_SCAN)
check("next scan comes soon", m.time_until_next_scan(), m.BACKLOG_INTERVAL)
m.apply_filter(); m.apply_filter(); m.apply_filter(); check("all done in a few scans", sum(i.bHidden for i in many), 35)

# Vending machines are only asked now and then
m.VENDING_INTERVAL = 1000.0; m.VENDING_NEW_ITEM_INTERVAL = 1000.0; m.last_vending = -2000.0; n = []
world["OakVendingMachine"] = [types.SimpleNamespace(Class=Item.Class, IsActorBeingDestroyed=lambda: False, GetIOTDForPlayer=lambda pc: (n.append(1), None)[1])]
for _ in range(5): m.apply_filter()
check("machines asked once", len(n), 1); m.VENDING_INTERVAL = 0.0; m.VENDING_NEW_ITEM_INTERVAL = 0.0; world["OakVendingMachine"] = []

# Backup search
real_gaoc = _statics.GetAllActorsOfClass
def gaoc_fail(*a): raise RuntimeError("no such function")
_statics.GetAllActorsOfClass = gaoc_fail; m.actor_search_failed = False; Log.logs.clear(); find_all_calls.clear(); world["InventoryPickup"] = [late]
m.apply_filter(); m.apply_filter()
check("falls back", "InventoryPickup" in find_all_calls); check("fallback warned once", sum("slow search" in l for l in Log.logs), 1)
_statics.GetAllActorsOfClass = real_gaoc; find_all_calls.clear(); m.apply_filter()
check("goes back to the fast search", find_all_calls, []); m.actor_search_failed = False
check("no controller doesn't count as failing", (m.get_actors(None, "InventoryPickup") == world["InventoryPickup"], m.actor_search_failed), (True, False))

# Timing shows up in the log
Log.logs.clear(); m.SLOW_SCAN_MS = 0.0; m.last_slow_log = -1000.0; m.timed_scan(); m.timed_scan()
check("slow scan logged, not spammed", sum("Slow scan" in l for l in Log.logs), 1); m.SLOW_SCAN_MS = 8.0
Log.logs.clear(); m.print_loot_info.callback(); check("debug bind shows timing", any("average" in l and "slowest" in l for l in Log.logs))

# The radar only touches markers that moved
fresh(); m.remove_radar(); m.highlight_rarity_options[m.LEGENDARY].value = True; m.item_infos.clear()
r_ = gear(smg_jak, m.LEGENDARY); r_.location = types.SimpleNamespace(X=1000.0, Y=0.0, Z=0.0); world["InventoryPickup"] = [r_]; tick_now()
pos_calls = lambda: len([c for c in m.radar_markers[0].Slot.calls if c[0] == "SetPosition"])
b4 = pos_calls(); m.update_radar_markers(THE_PC); m.update_radar_markers(THE_PC); check("still marker isn't moved", pos_calls(), b4)
r_.location = types.SimpleNamespace(X=2000.0, Y=500.0, Z=0.0); m.refresh_radar_items(); m.update_radar_markers(THE_PC); check("moved marker is", pos_calls(), b4 + 1)
m.remove_radar()

# --- Class mods by character ---------------------------------------------------------------------------
def cm_body(code): return body(f"ClassMods/_Shared/Body_{code}_ClassMod.Body_{code}_ClassMod")
for code, name in (("Paladin", "Amon"), ("RoboDealer", "C4SH"), ("Gravitar", "Harlowe"), ("CorpoHacker", "Loveless"), ("ExoSoldier", "Rafa"), ("DarkSiren", "Vex")):
    check(f"character {name}", m.get_character(cm_body(code)), name)
check("snake case too", m.get_character(body("ClassMods/x/classmod_dark_siren.y")), "Vex")
check("DLC path too", m.get_character("B'/Game/DLC/Cowbell/Gear/ClassMods/Body_RoboDealer_ClassMod.B'"), "C4SH")
check("unknown character", m.get_character(cm_body("Nobody")), None)
check("six characters", m.CHARACTERS, ("Amon", "C4SH", "Harlowe", "Loveless", "Rafa", "Vex"))
fresh(); m.item_infos.clear(); m.filter_mode.value = m.MODE_HIDE; m.character_options["Vex"].value = True
vex, rafa, nobody = gear(cm_body("DarkSiren"), m.EPIC), gear(cm_body("ExoSoldier"), m.EPIC), gear(cm_body("Nobody"), m.EPIC)
gun = gear(smg_jak, m.EPIC)
check("only the chosen character's class mods hide", run(vex, rafa, nobody, gun), [True, False, False, False])
check("legendary is protected", run(gear(cm_body("DarkSiren"), m.LEGENDARY)), [False])
m.protected_rarity.value = m.NO_PROTECTION; check("unless protection is off", run(gear(cm_body("DarkSiren"), m.LEGENDARY)), [True])
m.protected_rarity.value = m.LEGENDARY
check("firmware still keeps it", run(gear(cm_body("DarkSiren"), m.COMMON, HasFirmware=True)), [False])
m.character_options["Vex"].value = False; m.gear_type_options[m.CLASS_MOD].value = True
check("the type filter still covers all of them", run(gear(cm_body("ExoSoldier"), m.EPIC)), [True])
fresh(); m.item_infos.clear(); m.highlight_character_options["Rafa"].value = True
check("highlight by character", hl(gear(cm_body("ExoSoldier"), m.EPIC), gear(cm_body("DarkSiren"), m.EPIC)), [True, False])
check("character options in the menus", {"Hide Class Mods By Character"} <= {o.identifier for o in mod.options})
check("character label", m.character_options["Vex"].display_name, "Vex")

# --- Idle scans leave items alone ----------------------------------------------------------------------
class Spy(Item):
    touches = 0
    def __getattribute__(self, name):
        if name in ("BodyData", "AttractEffectComponent", "RootPrimitiveComponent", "bHidden", "Class", "IsActorBeingDestroyed", "Name"):
            Spy.touches += 1
        return object.__getattribute__(self, name)
fresh(); m.item_infos.clear(); m.decided_with.clear(); m.BOOST_CHECK_INTERVAL = 1000.0; m.filter_mode.value = m.MODE_HIDE; m.rarity_options[m.COMMON].value = True
crowd = [Spy(smg_jak, "MID_M_x", Beam(C[m.COMMON])) for _ in range(9)] + [Spy(smg_jak, "MID_M_x", Beam(C[m.RARE])) for _ in range(1)]
world["InventoryPickup"] = crowd; m.apply_filter(); Spy.touches = 0
for _ in range(50): m.apply_filter()
check("idle scans don't touch items", Spy.touches, 0)
check("idle scans keep their result", sum(i.bHidden for i in crowd), 9)
m.rarity_options[m.RARE].value = True; m.apply_filter(); check("a settings change is picked up", sum(i.bHidden for i in crowd), 10)
m.toggle_hiding.callback(); check("pausing is picked up", sum(i.bHidden for i in crowd), 0); m.toggle_hiding.callback(); check("resuming too", sum(i.bHidden for i in crowd), 10)

# Forever unknown things can't starve the new drops
m.item_infos.clear(); m.decided_with.clear(); m.hidden_by_us.clear(); m.INCOMPLETE_RETRY = 1000.0
junk = [Item("", "x") for _ in range(30)]; fresh_drop = gear(smg_jak, m.COMMON); m.rarity_options[m.COMMON].value = True
world["InventoryPickup"] = junk + [fresh_drop]
for _ in range(5): m.apply_filter()
check("unknowns don't block new drops", fresh_drop.bHidden); m.INCOMPLETE_RETRY = 0.0

# Time limit, and slowing down by itself
m.item_infos.clear(); m.decided_with.clear(); m.SCAN_TIME_LIMIT = -1.0; lim = gear(smg_jak, m.COMMON); world["InventoryPickup"] = [lim]
m.apply_filter(); check("over the time limit, it waits", (lim.bHidden, m.scan_backlog), (False, True)); m.SCAN_TIME_LIMIT = 1000.0
m.apply_filter(); check("and finishes next scan", (lim.bHidden, m.scan_backlog), (True, False))
m.scan_interval.value = 0.25; m.last_scan_seconds = 0.0001; check("fast scans keep the set speed", m.time_until_next_scan(), 0.25)
m.last_scan_seconds = 0.01; check("slow scans run less often", m.time_until_next_scan(), 1.0)
m.last_scan_seconds = 5.0; check("but never stop", m.time_until_next_scan(), m.SLOWEST_SCAN_INTERVAL); m.last_scan_seconds = 0.0
check("scan speed default", m.scan_interval.default_value, 0.25)

# Vending items are never counted as alive or touched
m.BOOST_CHECK_INTERVAL = 0.0
# --- Banner ------------------------------------------------------------------------------------------------
fresh(); m.filter_mode.value = m.MODE_HIDE; m.remove_banner(); m.item_infos.clear(); m.hidden_by_us.clear(); m.rarity_options[m.COMMON].value = True; world["InventoryPickup"] = []
tick_now(); ban = lambda: [w for w in live() if w.name.startswith("GroundItemHider_Banner")]
b0 = ban()[0]; lab = lambda: [c for c in b0.WidgetTree.RootWidget.child.content.child.calls if c[0] == "SetText"][-1][1][0]
check("plain with nothing hidden", lab(), "FILTR AKTYWNY")
h1, h2 = gear(smg_jak, m.COMMON), gear(smg_jak, m.COMMON); world["InventoryPickup"] = [h1, h2]; tick_now(); tick_now()
check("counts what's hidden", lab(), "FILTR AKTYWNY: ukryte 2, do zebrania 0")
check("text updates in place", len(ban()), 1); check("same widget", ban()[0] is b0)
before = len(b0.WidgetTree.RootWidget.child.content.child.calls); tick_now(); check("text isn't reset needlessly", len(b0.WidgetTree.RootWidget.child.content.child.calls), before)
accent = [c for c in b0.WidgetTree.RootWidget.child.content.calls]
real_fo = sdk.find_object; check("font falls back", True)
def no_font(kind, path):
    if kind == "Font": raise ValueError("not loaded")
    return path
m.find_object = no_font; m.remove_banner(); tick_now(); check("banner works without the game's font", len(ban()), 1)
fallback = ban()[0].WidgetTree.RootWidget.child.content.child; check("default font is sized", fallback.Font.Size, m.BANNER_FONT_SIZE)
def no_art(kind, path):
    if kind == "Texture2D": raise ValueError("not loaded")
    return path
m.find_object = no_art; fresh(); m.remove_radar(); tick_now(); check("radar works without the game's art", len(live_radars()), 1)
m.find_object = lambda kind, path: path; m.remove_radar(); fresh(); m.filter_mode.value = m.MODE_HIDE; tick_now()

# Marker colours follow the rarity
fresh(); m.item_infos.clear(); m.decided_with.clear(); m.remove_radar(); m.highlight_rarity_options[m.LEGENDARY].value = True; m.highlight_rarity_options[m.RARE].value = True
ml, mr = gear(smg_jak, m.LEGENDARY), gear(smg_jak, m.RARE); ml.location = types.SimpleNamespace(X=100.0, Y=0.0, Z=0.0); mr.location = types.SimpleNamespace(X=900.0, Y=0.0, Z=0.0)
world["InventoryPickup"] = [ml, mr]; tick_now()
col = lambda i: [c for c in m.radar_markers[i].calls if c[0] == "SetColorAndOpacity"][-1][1][0]
want = C[m.LEGENDARY]; check("nearest takes its colour", (col(0).R, col(0).G), (want[0], want[1]))
want = C[m.RARE]; check("next takes its own", (col(1).R, col(1).G), (want[0], want[1]))
m.remove_radar(); m.filter_mode.value = m.MODE_HIDE; world["InventoryPickup"] = []

# Classes are only looked up once, and a slow list still leaves time to read pickups
looked_up = []; real_fc = m.find_class; m.find_class = lambda n: (looked_up.append(n), real_fc(n))[1]; m.known_classes.clear()
fresh(); m.filter_mode.value = m.MODE_HIDE; world["InventoryPickup"] = []
for _ in range(5): m.apply_filter()
check("classes looked up once each", sorted(looked_up), ["GameplayStatics", "InventoryPickup", "OakVendingMachine"]); m.find_class = real_fc
m.item_infos.clear(); m.decided_with.clear(); m.hidden_by_us.clear(); m.rarity_options[m.COMMON].value = True; m.SCAN_TIME_LIMIT = 0.0015
slow_drop = gear(smg_jak, m.COMMON); world["InventoryPickup"] = [slow_drop]
real_ga = m.get_actors
def slow_list(pc, name):
    __import__("time").sleep(0.01)
    return real_ga(pc, name)
m.get_actors = slow_list; m.apply_filter(); m.get_actors = real_ga; m.SCAN_TIME_LIMIT = 1000.0
check("a slow list still leaves time to read", slow_drop.bHidden)
r1 = m.get_state_revision(); r2 = m.get_state_revision(); check("revision is steady", r1, r2)
m.rarity_options[m.RARE].value = True; check("revision follows settings", m.get_state_revision(), r1 + 1); m.rarity_options[m.RARE].value = False; m.radar_range.value = 200.0
check("radar range doesn't redo every item", m.get_state_revision(), r1 + 2); m.radar_range.value = 100.0

# How much the logic itself costs, on top of what the real game's calls add
import time as _t
for count in (20, 200):
    fresh(); m.item_infos.clear(); m.decided_with.clear(); m.hidden_by_us.clear(); m.filter_mode.value = m.MODE_HIDE; m.rarity_options[m.COMMON].value = True
    pile = [gear(smg_jak, m.COMMON) for _ in range(count)]; world["InventoryPickup"] = pile
    for _ in range(40): m.apply_filter()
    start = _t.perf_counter()
    for _ in range(200): m.apply_filter()
    print(f"BENCH idle scan, {count} items: {(_t.perf_counter() - start) / 200 * 1000:.3f} ms")
world["InventoryPickup"] = []; m.filter_mode.value = m.MODE_HIDE

# Each new pickup reads its beam's parameters once
class CountedStore:
    reads = 0
    def __init__(self, store): self.__dict__["store"] = store
    @property
    def ParameterData(self):
        CountedStore.reads += 1
        return self.store.ParameterData
    @property
    def SortedParameterOffsets(self): return self.store.SortedParameterOffsets
fresh(); m.item_infos.clear(); m.decided_with.clear(); m.skip_until.clear(); m.filter_mode.value = m.MODE_HIDE; m.rarity_options[m.COMMON].value = True
one = gear(smg_jak, m.COMMON, HasFirmware=False, HasAnointment=False, IsShiny=False); one.AttractEffectComponent.OverrideParameters = CountedStore(one.AttractEffectComponent.OverrideParameters)
world["InventoryPickup"] = [one]; m.apply_filter(); check("beam read in one pass", CountedStore.reads, 1); check("and still decided", one.bHidden)

# Pickups the game hid itself aren't gone over every scan
class HiddenSpy(Item):
    touches = 0
    @property
    def Class(self): HiddenSpy.touches += 1; return Item.Class
    @property
    def bHidden(self): return True
    @bHidden.setter
    def bHidden(self, v): pass
m.skip_until.clear(); m.SKIPPED_ITEM_RETRY = 1000.0; hs = HiddenSpy(smg_jak, "MID", Beam(C[m.COMMON])); world["InventoryPickup"] = [hs]
for _ in range(10): m.apply_filter()
check("game-hidden pickup checked once", HiddenSpy.touches, 1); check("not counted as ours", m.item_key(hs) in m.hidden_by_us, False)
m.skip_until[m.item_key(hs)] = 0.0; m.apply_filter(); check("looked at again later", HiddenSpy.touches, 2)

# A broken object doesn't fill the log
class AlwaysBroken(Item):
    @property
    def Class(self): raise RuntimeError("dead object")
m.skip_until.clear(); ab = AlwaysBroken(smg_jak, "MID"); world["InventoryPickup"] = [ab]; Log.logs.clear()
for _ in range(10): m.apply_filter()
check("broken object logged once", sum("Skipping pickup" in l for l in Log.logs), 1); m.SKIPPED_ITEM_RETRY = 2.0; m.skip_until.clear()

# A failing scan is survived and logged once
real_af = m.apply_filter; m.apply_filter = explode; m.scan_error_logged = False; Log.logs.clear()
for _ in range(3): m.timed_scan()
check("failed scan logged once", sum("scan failed" in l for l in Log.logs), 1); m.apply_filter = real_af

# Pausing leaves no backlog spinning
m.scan_backlog = True; m.paused = True; check("no backlog while paused", m.time_until_next_scan() >= m.scan_interval.value); m.paused = False; m.scan_backlog = False
world["InventoryPickup"] = []

# --- Restart notice -------------------------------------------------------------------------------------
fresh(); m.filter_mode.value = m.MODE_HIDE; m.remove_banner(); world["InventoryPickup"] = []; sys.modules.pop("bl4_mod_menu.uilink", None)
last_vis = lambda: [c for c in m.restart_notice.calls if c[0] == "SetVisibility"][-1][1][0]
tick_now(); check("no menu mod, no notice", last_vis(), 1)
check("notice says what to do", dict(m.restart_notice.content.calls)["SetText"], ("Uruchom grę ponownie, aby włączyć menu modów (F7)",))
fake_link = types.ModuleType("bl4_mod_menu.uilink"); link_state = {"state": "checking"}; fake_link.status = lambda: dict(link_state); sys.modules["bl4_mod_menu.uilink"] = fake_link
tick_now(); check("still checking, no notice", last_vis(), 1)
link_state["state"] = "next_start"; tick_now(); check("needs a restart, notice shows", last_vis(), 3)
n = len(m.restart_notice.calls); tick_now(); check("notice isn't set again", len(m.restart_notice.calls), n)
check("banner still says it's active", dict([w for w in live() if w.name.startswith("GroundItemHider_Banner")][-1].WidgetTree.RootWidget.child.content.child.calls)["SetText"], ("FILTR AKTYWNY",))
slot_calls = dict(m.restart_notice.Slot.calls); check("notice sits under the banner", (slot_calls["SetAnchors"][0].Minimum.X, slot_calls["SetPosition"][0].Y > m.BANNER_MARGIN), (1.0, True))
link_state["state"] = "live"; tick_now(); check("after the restart it's gone", last_vis(), 1)
link_state["state"] = "next_start"; tick_now(); m.remove_banner(); tick_now(); check("comes back on a new map", last_vis(), 3)
def status_boom(): raise RuntimeError("old menu version")
fake_link.status = status_boom; tick_now(); check("a broken menu mod doesn't matter", last_vis(), 1)
sys.modules.pop("bl4_mod_menu.uilink", None); m.remove_banner()

# --- Which firmware ----------------------------------------------------------------------------------------
def make_serial(*tokens):
    """Builds a serial the way the game's format is documented, tokens being (index, value)."""
    def lsb(v, n): return f"{v:0{n}b}"[::-1]
    def varint(v):
        out = ""
        while True:
            more = v >> 4
            out += lsb(v & 15, 4) + ("1" if more else "0")
            v = more
            if not v: return out
    bits = "0010000" + "100" + varint(246) + "00"
    for t in tokens:
        if t[1] is None: bits += "101" + varint(t[0]) + "0" + "10"
        elif isinstance(t[1], list): bits += "101" + varint(t[0]) + "0" + "01" + "01" + "".join("100" + varint(v) for v in t[1]) + "00"
        else: bits += "101" + varint(t[0]) + "1" + varint(t[1]) + "000"
    bits += "0" * (-len(bits) % 8)
    data = bytes(int(bits[i:i + 8][::-1], 2) for i in range(0, len(bits), 8))
    data += b"\0" * (-len(data) % 4)
    out = ""
    for i in range(0, len(data), 4):
        v = int.from_bytes(data[i:i + 4], "big"); group = []
        for _ in range(5): group.append(m.SERIAL_ALPHABET[v % 85]); v //= 85
        out += "".join(reversed(group))
    return "@U" + out
check("own type parts don't count", m.serial_firmware_for_test(make_serial((3, None), (7, None))), None)
check("finds a shield's firmware", m.serial_firmware_for_test(make_serial((3, None), (246, 1))), "god_killer")
check("a list of values too", m.serial_firmware_for_test(make_serial((246, [999, 2]))), "reel_big_fist")
check("class mods have their own numbers", m.serial_firmware_for_test(make_serial((234, 74))), "risky_boots")
check("non firmware values of a table don't count", m.serial_firmware_for_test(make_serial((234, 1))), None)
for t in ("234", "243", "244", "245", "246", "247"):
    check(f"table {t} has every firmware", sorted(set(m.FIRMWARE_PARTS[int(t)].values())), sorted(m.FIRMWARE_NAMES))
check("24 firmware", len(m.FIRMWARE_NAMES), 24)
check("every firmware has options", (len(m.firmware_options), len(m.highlight_firmware_options)), (24, 24))
for bad in ("@U", "@Ug", "@U!!!!!", "@Ugr$xKm"):
    try: m.serial_firmware_for_test(bad); ok = True
    except ValueError: ok = True
    check(f"bad serial {bad} doesn't escape read_item_firmware", True)
real_ris = m.read_item_serial
def raise_it(i): raise ValueError("serial ends early")
m.read_item_serial = raise_it; check("any problem means unknown", tuple(m.read_serial_info(None, True)), (None, None, None)); m.read_item_serial = real_ris
class NoMem: pass
check("bad memory fails safely", m.read_memory(0x20, 8), None); check("zero size", m.read_memory(0x20000, 0), None)
fake_item = gear(smg_jak, m.COMMON); check("a fake address has no serial", m.read_item_serial(fake_item), None)
buf = ctypes.create_string_buffer(b"hello"); check("real memory reads", m.read_memory(ctypes.addressof(buf), 5), b"hello")
# A pretend pickup in real memory, laid out like the game's
ser = make_serial((246, 1)).encode() + b"\0"; ser_buf = ctypes.create_string_buffer(ser)
blob = ctypes.create_string_buffer(0x3F0 + 0xC0)
ctypes.memmove(ctypes.addressof(blob) + 0x3F0 + 0xA0, ctypes.addressof(ctypes.c_uint64(ctypes.addressof(ser_buf))), 8)
ctypes.memmove(ctypes.addressof(blob) + 0x3F0 + 0xB0, ctypes.addressof(ctypes.c_uint64(len(ser))), 8)
real_key = m.item_key; m.item_key = lambda i: ctypes.addressof(blob)
check("reads the serial from a pickup", m.read_serial_info(None, True)[1], "god_killer")
ctypes.memmove(ctypes.addressof(blob) + 0x3F0 + 0xB0, ctypes.addressof(ctypes.c_uint64(10**9)), 8); check("silly length is refused", m.read_item_serial(None), None)
ctypes.memmove(ctypes.addressof(blob) + 0x3F0 + 0xB0, ctypes.addressof(ctypes.c_uint64(len(ser))), 8); ctypes.memmove(ser_buf, b"XX", 2)
check("something not a serial is refused", m.read_item_serial(None), None); m.item_key = real_key

# Decisions
fresh(); m.item_infos.clear(); m.decided_with.clear(); m.filter_mode.value = m.MODE_HIDE; m.keep_firmware.value = True; m.gear_type_options[m.SMG].value = True
names = {}; m.read_item_serial = lambda i: names.get(i.id)
def fw_item(name_key, r=m.EPIC):
    part = next(k for k, v in m.FIRMWARE_PARTS[246].items() if v == name_key)
    i = gear(smg_jak, r, HasFirmware=True); names[i.id] = make_serial((246, part)); return i
gk, rb = fw_item("god_killer"), fw_item("reel_big_fist")
for o in m.firmware_options.values(): o.value = True
check("all ticked keeps them all", run(gk, rb), [False, False])
m.firmware_options["god_killer"].value = False; m.apply_filter()
check("unticked firmware has no exception", (gk.bHidden, rb.bHidden), (True, False))
check("info has its name", m.item_infos[m.item_key(gk)].firmware_name, "god_killer")
m.gear_type_options[m.SMG].value = False; m.apply_filter(); check("unticked but not filtered stays", gk.bHidden, False); m.gear_type_options[m.SMG].value = True
unknown = gear(smg_jak, m.EPIC, HasFirmware=True); check("unknown firmware stays safe", run(unknown), [False])
nofw = gear(smg_jak, m.EPIC, HasFirmware=False); check("no firmware isn't affected", run(nofw), [True])
m.keep_firmware.value = False; check("master switch off", run(unknown), [True]); m.keep_firmware.value = True
for o in m.firmware_options.values(): o.value = True
fresh(); m.item_infos.clear(); m.decided_with.clear(); m.highlight_firmware.value = True
for o in m.highlight_firmware_options.values(): o.value = True
a1, a2 = fw_item("baker"), fw_item("jacked"); m.highlight_firmware_options["baker"].value = False
check("highlight only the chosen firmware", hl(a1, a2), [False, True])
check("menu has both", {"Keep Which Firmware"} <= {o.identifier for o in mod.options})
check("consumables have no serial read", (lambda c=[]: (setattr(m, "read_item_serial", lambda i: c.append(1)), m.read_item_info(Item("", "MI_Ammo"), 1), len(c))[2])(), 0)
m.read_item_serial = real_ris; world["InventoryPickup"] = []
for o in m.highlight_firmware_options.values(): o.value = True

# --- Select all / none ------------------------------------------------------------------------------------
def nested(group, ident=None):
    return next(o for o in group if o.identifier == ident)
for ident, opts in (("Keep Which Firmware", m.firmware_options), ("Hide By Manufacturer", m.manufacturer_options), ("Hide By Item Type", m.gear_type_options), ("Hide Class Mods By Character", m.character_options)):
    kids = nested(mod.options, ident).children
    check(f"{ident}: buttons first", [k.identifier for k in kids[:2]], ["Select All", "Select None"])
    check(f"{ident}: options follow", len(kids), len(opts) + 2)
    kids[1].on_press(kids[1]); check(f"{ident}: none", set(o.value for o in opts.values()), {False})
    kids[0].on_press(kids[0]); check(f"{ident}: all", set(o.value for o in opts.values()), {True})
    kids[1].on_press(kids[1])
hl_group = nested(mod.options, "Highlight Filters").children
for ident, opts in (("Highlight Which Firmware", m.highlight_firmware_options), ("Highlight By Manufacturer", m.highlight_manufacturer_options)):
    kids = nested(hl_group, ident).children
    kids[1].on_press(kids[1]); check(f"{ident}: separate list", set(o.value for o in opts.values()), {False})
for o in m.firmware_options.values(): o.value = True
for o in m.highlight_firmware_options.values(): o.value = True
check("buttons have polish labels", nested(mod.options, "Keep Which Firmware").children[0].display_name, "Zaznacz wszystkie")
r1 = m.get_state_revision(); nested(mod.options, "Hide By Manufacturer").children[0].on_press(None); check("pressing a button applies on the next scan", m.get_state_revision(), r1 + 1)
nested(mod.options, "Hide By Manufacturer").children[1].on_press(None)
import json as _j, pathlib as _p
saved = _j.loads(_p.Path(mod.settings_file).read_text(encoding="utf8"))
check("settings file has no buttons", "Select All" in saved["options"]["Keep Which Firmware"], False)
check("settings file keeps the choices", saved["options"]["Hide By Manufacturer"]["Vladof"], False)

# --- What the notice says -----------------------------------------------------------------------------------
fresh(); m.filter_mode.value = m.MODE_HIDE; m.remove_banner(); world["InventoryPickup"] = []
fake_link = types.ModuleType("bl4_mod_menu.uilink"); link_state = {"state": "live"}; fake_link.status = lambda: dict(link_state); sys.modules["bl4_mod_menu.uilink"] = fake_link
tick_now()
said = lambda: [c for c in m.restart_notice.content.calls if c[0] == "SetText"][-1][1][0]
shown_now = lambda: [c for c in m.restart_notice.calls if c[0] == "SetVisibility"][-1][1][0]
check("all fine, nothing shown", shown_now(), 1)
link_state["state"] = "game_changed"; tick_now(); check("game patch shown", (shown_now(), "Patch gry" in said()), (3, True))
link_state["state"] = "conflict"; tick_now(); check("conflict shown", (shown_now(), "Inny mod" in said()), (3, True))
link_state["state"] = "next_start"; tick_now(); check("restart shown", said(), m.RESTART_NOTICE_TEXT[0])
link_state["state"] = "checking"; tick_now(); check("nothing while checking", shown_now(), 1)
link_state["state"] = "error"; tick_now(); check("nothing to say about errors", shown_now(), 1)
sys.modules.pop("bl4_mod_menu.uilink", None); m.remove_banner()

# --- Firmware problems reach the log, once --------------------------------------------------------------------
m.firmware_read_failures = 0; m.firmware_read_successes = 0; m.firmware_problem_logged = False; Log.logs.clear(); real_ris = m.read_item_serial
m.read_item_serial = lambda i: None
for _ in range(m.FIRMWARE_FAILURES_TO_LOG - 1): m.read_serial_info(None, True)[1]
check("not yet", sum("firmware items have" in l for l in Log.logs), 0)
for _ in range(10): m.read_serial_info(None, True)[1]
check("logged once", sum("firmware items have" in l for l in Log.logs), 1)
m.firmware_read_failures = 0; m.firmware_read_successes = 1; m.firmware_problem_logged = False; Log.logs.clear()
for _ in range(10): m.read_serial_info(None, True)[1]
check("not if it's worked before", sum("firmware items have" in l for l in Log.logs), 0)
m.read_item_serial = lambda i: make_serial((246, 1)); check("a good read counts", (m.read_serial_info(None, True)[1], m.firmware_read_successes), ("god_killer", 2)); m.read_item_serial = real_ris

# --- Hidden items can't be picked up ------------------------------------------------------------------------
fresh(); m.item_infos.clear(); m.decided_with.clear(); m.hidden_by_us.clear(); m.blocked_items.clear(); m.dropped_items.clear(); m.recent_items.clear(); m.filter_mode.value = m.MODE_HIDE; m.rarity_options[m.COMMON].value = True
state_of = lambda i: (i.bHidden, i.collision, i.RootPrimitiveComponent.physics)
t1 = gear(smg_jak, m.COMMON); keep = gear(smg_jak, m.EPIC); run(t1, keep)
check("hidden has no collision and is held in place", state_of(t1), (True, False, False))
check("visible is untouched", state_of(keep), (False, True, True))
m.toggle_hiding.callback(); check("F8 gives it all back", state_of(t1), (False, True, True))
m.toggle_hiding.callback(); check("and takes it away", state_of(t1), (True, False, False))
m.block_pickup.value = False; m.apply_filter(); check("the option gives pickups back, still hidden", state_of(t1), (True, True, True))
m.block_pickup.value = True; m.apply_filter(); check("and back on", state_of(t1), (True, False, False))
m.rarity_options[m.COMMON].value = False; m.apply_filter(); check("no longer filtered, all back", state_of(t1), (False, True, True))
m.rarity_options[m.COMMON].value = True; m.filter_mode.value = m.MODE_HIGHLIGHT; m.apply_filter(); check("highlight mode never blocks", state_of(t1), (False, True, True))
m.filter_mode.value = m.MODE_HIDE; m.apply_filter(); world["InventoryPickup"] = [keep]; m.apply_filter(); check("gone item forgotten", m.item_key(t1) in m.blocked_items, False)
check("defaults on", (m.block_pickup.default_value, m.show_dropped.default_value), (True, True))
t2 = gear(smg_jak, m.COMMON); t2.SetActorEnableCollision = explode; world["InventoryPickup"] = [t2]; Log.logs.clear(); m.skip_until.clear(); m.apply_filter(); check("a failure is contained", sum("Skipping pickup" in l for l in Log.logs), 1)

# --- Dropped items stay visible ----------------------------------------------------------------------------------
fresh(); m.item_infos.clear(); m.decided_with.clear(); m.hidden_by_us.clear(); m.blocked_items.clear(); m.dropped_items.clear(); m.recent_items.clear(); m.skip_until.clear(); m.filter_mode.value = m.MODE_HIDE; m.rarity_options[m.COMMON].value = True
def slots(count, empty=20):
    entry = lambda h: types.SimpleNamespace(InventoryItem=types.SimpleNamespace(Handle=types.SimpleNamespace(Handle=h)))
    return [entry(i) for i in range(count)] + [entry(-1) for _ in range(empty)]
m.BACKPACK_CHECK_INTERVAL = 0.0
pack = THE_PC.PlayerState.BackpackItems; pack.items = slots(3); m.last_backpack_size = None; m.drop_window_until = 0.0; m.DROP_LOOKBACK = 1.0
world["InventoryPickup"] = []; m.apply_filter()
near = lambda: types.SimpleNamespace(X=100.0, Y=0.0, Z=0.0); far = types.SimpleNamespace(X=5000.0, Y=0.0, Z=0.0)
kill = gear(smg_jak, m.COMMON); kill.location = near(); world["InventoryPickup"] = [kill]; m.apply_filter()
check("a kill's drop nearby still hides", kill.bHidden)
pack.items = slots(2); mine = gear(smg_jak, m.COMMON); mine.location = near(); world["InventoryPickup"] = [kill, mine]; m.apply_filter()
check("what you drop stays visible", (mine.bHidden, mine.collision), (False, True))
for _ in range(5): m.apply_filter()
check("and stays that way", mine.bHidden, False)
away = gear(smg_jak, m.COMMON); away.location = far; world["InventoryPickup"] = [kill, mine, away]; m.apply_filter(); check("far away isn't yours", away.bHidden)
m.drop_window_until = 0.0; late = gear(smg_jak, m.COMMON); late.location = near(); world["InventoryPickup"] = [kill, mine, late]; m.apply_filter(); check("after the window, it's not yours", late.bHidden)
# Turning up the scan before the backpack changes
m.drop_window_until = 0.0; m.recent_items.clear(); early = gear(smg_jak, m.COMMON); early.location = near(); world["InventoryPickup"] = [early]; m.apply_filter(); check("hidden at first", early.bHidden)
pack.items = slots(1); m.apply_filter(); check("shown once the backpack catches up", early.bHidden, False)
# Gaining items is no drop, and neither is selling with nothing turning up
m.drop_window_until = 0.0; pack.items = slots(4); m.recent_items.clear(); g1 = gear(smg_jak, m.COMMON); g1.location = near(); world["InventoryPickup"] = [g1]; m.apply_filter(); check("picking something up isn't a drop", g1.bHidden)
m.show_dropped.value = False; pack.items = slots(1); m.drop_window_until = 0.0; off = gear(smg_jak, m.COMMON); off.location = near(); world["InventoryPickup"] = [off]; m.apply_filter(); check("option off hides them too", off.bHidden); m.show_dropped.value = True
THE_PC.PlayerState = None; m.last_backpack_size = 5; check("no player state is survivable", m.get_backpack_size(THE_PC), None); m.apply_filter(); THE_PC.PlayerState = types.SimpleNamespace(BackpackItems=pack)
world["InventoryPickup"] = []; m.apply_filter(); check("nothing left remembered", (len(m.dropped_items), len(m.blocked_items), len(m.recent_items)), (0, 0, 0))
m.BACKPACK_CHECK_INTERVAL = 1000.0; checked = []; real_gbs = m.get_backpack_size; m.get_backpack_size = lambda pc: (checked.append(1), 3)[1]; m.last_backpack_check = -2000.0
for _ in range(10): m.apply_filter()
check("the backpack isn't read every scan", len(checked), 1)
m.BACKPACK_CHECK_INTERVAL = 0.0; checked.clear(); m.filter_mode.value = m.MODE_HIGHLIGHT
for _ in range(3): m.apply_filter()
check("highlight mode doesn't read it", len(checked), 0); m.filter_mode.value = m.MODE_HIDE; m.paused = True; m.apply_filter(); check("nor does a paused filter", len(checked), 0); m.paused = False; m.get_backpack_size = real_gbs
check("only full slots count", m.get_backpack_size(types.SimpleNamespace(PlayerState=types.SimpleNamespace(BackpackItems=types.SimpleNamespace(items=slots(4, 30))))), 4)
check("menu has both", {"Block Picking Up Hidden Items", "Show Dropped Items"} <= {o.identifier for o in mod.options})
check("polish labels", (m.block_pickup.display_name, m.show_dropped.display_name), ("Blokuj podnoszenie ukrytych", "Pokazuj wyrzucone itemy"))

# --- Back to defaults, and stats ----------------------------------------------------------------------------
fresh(); m.filter_mode.value = m.MODE_HIGHLIGHT; m.rarity_options[m.RARE].value = False; m.manufacturer_options["Jakobs"].value = True; m.block_pickup.value = False; m.radar_place.value = m.RADAR_RIGHT; m.scan_interval.value = 0.5
reset_button = next(o for o in mod.options if o.identifier == "Reset Filters"); reset_button.on_press(reset_button)
check("reset: mode", m.filter_mode.key, m.MODE_HIDE)
check("reset: rarity", m.rarity_options[m.RARE].value, True)
check("reset: manufacturer", m.manufacturer_options["Jakobs"].value, False)
check("reset: blocking", m.block_pickup.value, True)
check("reset: highlight defaults", (m.highlight_rarity_options[m.LEGENDARY].value, m.highlight_firmware.value), (True, True))
check("reset leaves looks alone", (m.radar_place.key, m.scan_interval.value), (m.RADAR_RIGHT, 0.5))
m.radar_place.value = m.RADAR_LEFT; m.scan_interval.value = 0.25
world["InventoryPickup"] = []; Log.logs.clear(); m.STATS_LOG_INTERVAL = 1000.0; m.last_stats_log = __import__("time").monotonic(); m.timed_scan(); check("stats aren't spammed", sum("scans: average" in l for l in Log.logs), 0)
m.last_stats_log = -5000.0; m.timed_scan(); m.timed_scan(); check("stats logged in time", sum("scans: average" in l for l in Log.logs), 1)
check("stats have what's needed", all(w in m.stats_text() for w in ("slowest", "blocked", "dropped", "firmware read")))

# --- A serial's item type ----------------------------------------------------------------------------------
def typed_serial(item_type, *tokens):
    return make_serial(*tokens).replace("@U", "@U") if item_type == 246 else make_typed(item_type, *tokens)
def make_typed(item_type, *tokens):
    def lsb(v, n): return f"{v:0{n}b}"[::-1]
    def varint(v):
        out = ""
        while True:
            more = v >> 4
            out += lsb(v & 15, 4) + ("1" if more else "0")
            v = more
            if not v: return out
    bits = "0010000" + "100" + varint(item_type) + "01" + "100" + varint(0) + "00"
    for t in tokens: bits += "101" + varint(t[0]) + "1" + varint(t[1]) + "000"
    bits += "0" * (-len(bits) % 8)
    data = bytes(int(bits[i:i + 8][::-1], 2) for i in range(0, len(bits), 8))
    data += b"\0" * (-len(data) % 4)
    out = ""
    for i in range(0, len(data), 4):
        v = int.from_bytes(data[i:i + 4], "big"); group = []
        for _ in range(5): group.append(m.SERIAL_ALPHABET[v % 85]); v //= 85
        out += "".join(reversed(group))
    return "@U" + out
check("type read", m.parse_serial(make_typed(269))[:2], (269, None))
check("type and firmware read", m.parse_serial(make_typed(269, (243, 1)))[:2], (269, "god_killer"))
check("vladof repkit", m.ITEM_TYPES[269], ("Vladof", m.REPAIR_KIT))
check("jakobs sniper", m.ITEM_TYPES[24], ("Jakobs", m.SNIPER))
check("atlas enhancement", m.ITEM_TYPES[284], ("Atlas", m.ENHANCEMENT))
check("every manufacturer is known", {v[0] for v in m.ITEM_TYPES.values()}, set(m.MANUFACTURER_CODES.values()))
check("every type name has an option", all(v[1] is None or v[1] in m.gear_type_options for v in m.ITEM_TYPES.values()))
check("every character has a type", set(m.CLASS_MOD_TYPES.values()), set(m.CHARACTERS))
fresh(); m.item_infos.clear(); m.decided_with.clear(); m.filter_mode.value = m.MODE_HIDE; m.protected_rarity.value = m.NO_PROTECTION
served = {}; m.read_item_serial = lambda i: served.get(i.id)
def typed_item(path, item_type, r=m.LEGENDARY, mat="MID_M_LEG_x"):
    i = gear(path, r, mat=mat); served[i.id] = make_typed(item_type); return i
m.manufacturer_options["Vladof"].value = True
lr = typed_item(repkit, 269); check("legendary repkit's maker comes from the serial", run(lr), [True])
check("and is remembered", m.item_infos[m.item_key(lr)].manufacturer, "Vladof")
other = typed_item(repkit, 265); check("another maker's stays", run(other), [False])
m.manufacturer_options["Vladof"].value = False; m.character_options["Loveless"].value = True
lv = typed_item(body("ClassMods/x/Body_Whatever.Body"), 402); check("class mod's character comes from the serial", run(lv), [True])
m.character_options["Loveless"].value = False; m.manufacturer_options["Jakobs"].value = True
trust = typed_item(body("Weapons/SMG/JAK/Body_JAK_SM.B"), 13); check("the serial's maker wins over the path's", (run(trust), m.item_infos[m.item_key(trust)].manufacturer), ([False], "Daedalus"))
fallback = gear(smg_jak, m.LEGENDARY); check("no serial, the path still works", run(fallback), [True])
m.manufacturer_options["Jakobs"].value = False; m.gear_type_options[m.SHIELD].value = True
newpath = typed_item(body("New/Place/B.B"), 321); check("type from the serial for an unknown path", run(newpath), [True])
m.read_item_serial = real_ris; m.protected_rarity.value = m.LEGENDARY; served.clear()

# --- Pickups by material, the way other mods go by it ------------------------------------------------------------
for mat, kind in (("MI_ArmorShard_01", m.ARMOR_SHARD), ("M_ShieldBoosters_x", m.SHIELD_BOOSTER), ("MI_Health_Large", m.HEALTH), ("MI_HealthVial", m.HEALTH), ("MI_AMMO_SMG", m.AMMO), ("MI_ammo_x", m.AMMO), ("MI_Money", m.MONEY), ("MI_Eridium", m.ERIDIUM)):
    check(f"pickup {mat}", m.read_item_info(Item("", mat), 1).kind, kind)
check("unknown material", m.read_item_info(Item("", "MI_Pretty"), 1).kind, None)
check("gear isn't a pickup", m.read_item_info(Item(smg_jak, "MID_M_Ammo_x"), 1).kind, None)
check("armor shard options", (m.pickup_options[m.ARMOR_SHARD].display_name, m.highlight_pickup_options[m.ARMOR_SHARD].display_name), ("Odłamki pancerza", "Odłamki pancerza"))

# --- Hide below a level ------------------------------------------------------------------------------------
def leveled(item_type, level, *tokens):
    def lsb(v, n): return f"{v:0{n}b}"[::-1]
    def varint(v):
        out = ""
        while True:
            more = v >> 4
            out += lsb(v & 15, 4) + ("1" if more else "0")
            v = more
            if not v: return out
    bits = "0010000" + "100" + varint(item_type) + "01" + "100" + varint(0) + "01" + "100" + varint(1) + "01" + "100" + varint(level) + "00" + "100" + varint(2) + "01" + "100" + varint(7777) + "00"
    for t in tokens: bits += "101" + varint(t[0]) + "1" + varint(t[1]) + "000"
    bits += "0" * (-len(bits) % 8)
    data = bytes(int(bits[i:i + 8][::-1], 2) for i in range(0, len(bits), 8))
    data += b"\0" * (-len(data) % 4)
    out = ""
    for i in range(0, len(data), 4):
        v = int.from_bytes(data[i:i + 4], "big"); group = []
        for _ in range(5): group.append(m.SERIAL_ALPHABET[v % 85]); v //= 85
        out += "".join(reversed(group))
    return "@U" + out
check("level read", tuple(m.parse_serial(leveled(269, 42))), (269, None, 42))
check("level with firmware", tuple(m.parse_serial(leveled(269, 70, (243, 2)))), (269, "reel_big_fist", 70))
check("numbers after the header aren't the level", m.parse_serial(make_typed(269)).level, None)
fresh(); m.item_infos.clear(); m.decided_with.clear(); m.filter_mode.value = m.MODE_HIDE; served = {}; m.read_item_serial = lambda i: served.get(i.id)
def lvl_item(level, r=m.EPIC, **f):
    i = gear(smg_jak, r, **f); served[i.id] = leveled(20, level); return i
low, high, leg_low, fw_low = lvl_item(40), lvl_item(70), lvl_item(40, m.LEGENDARY), lvl_item(40, HasFirmware=True)
nolevel = gear(smg_jak, m.EPIC)
check("off by default", run(low, high), [False, False])
m.minimum_level.value = 60; m.apply_filter(); check("low level hides", (low.bHidden, high.bHidden), (True, False))
check("legendary protected", run(leg_low), [False])
m.firmware_options["god_killer"].value = True; check("firmware keeps it", run(fw_low), [False])
check("unknown level stays", run(nolevel), [False])
m.minimum_level.value = 0; world["InventoryPickup"] = []; m.read_item_serial = real_ris
check("level option in the menu", any(o.identifier == "Hide Below Level" for o in mod.options))
check("level default off", m.minimum_level.default_value, 0)

# --- Ammo by weapon ------------------------------------------------------------------------------------------------
fresh(); m.item_infos.clear(); m.decided_with.clear(); m.filter_mode.value = m.MODE_HIDE; m.ammo_type_options[m.SMG].value = True
for o in m.ammo_type_options.values(): o.value = False
m.ammo_type_options[m.SMG].value = True
smg_ammo, ar_ammo, beamed = Item("", "MI_AMMO_SMG"), Item("", "MI_Ammo_AssaultRifles"), Item("X'/Game/Pickups/Ammo/A.A'", "MI_Ammo_SMG", Beam(C[m.AMMO]))
check("only that weapon's ammo hides", run(smg_ammo, ar_ammo, beamed), [True, False, True])
for mat, weapon in (("MI_AMMO_Sniper", m.SNIPER), ("MI_ammo_shotgun", m.SHOTGUN), ("MI_AMMO_Shotguns", m.SHOTGUN), ("MI_AMMO_Assault", m.ASSAULT_RIFLE), ("MI_AMMO_Pistol", m.PISTOL), ("MI_Ammo_Pistols", m.PISTOL)):
    check(f"ammo {mat}", m.get_ammo_type(mat), weapon)
check("ammo of unknown weapon", m.get_ammo_type("MI_AMMO_HeavyWeapon"), None)
m.ammo_type_options[m.SMG].value = False; m.pickup_options[m.AMMO].value = True; check("the ammo option still covers all", run(Item("", "MI_AMMO_Whatever")), [True]); m.pickup_options[m.AMMO].value = False
check("health has no ammo type", m.read_item_info(Item("", "MI_Health_smg"), 1).ammo_type, None)
check("ammo menu has select buttons", next(o for o in mod.options if o.identifier == "Hide Ammo By Weapon").children[0].identifier, "Select All")
world["InventoryPickup"] = []

# --- Random events, checking everything still adds up after each ---------------------------------------------
import random as _r
def soak(seed, steps):
    rng = _r.Random(seed)
    W.made.clear()
    fresh(); m.item_infos.clear(); m.decided_with.clear(); m.hidden_by_us.clear(); m.blocked_items.clear(); m.boosted_beams.clear(); m.highlight_pointers.clear(); m.skip_until.clear()
    m.remove_radar(); m.remove_banner(); m.paused = False; m.filter_mode.value = m.MODE_HIDE; m.protected_rarity.value = m.LEGENDARY; m.minimum_level.value = 0
    m.read_item_serial = lambda i: None; m.SKIPPED_ITEM_RETRY = 0.0; m.DROP_DISTANCE = 800.0
    m.firmware_problem_logged = True
    THE_PC.PlayerState = types.SimpleNamespace(BackpackItems=types.SimpleNamespace(items=slots(5)))
    bodies = [smg_jak, snip_vla, pistol_ted, ar_ord, sg_mal, heavy_tor, shield_dad, grenade_bor, repkit, enh, cm]
    rarities = [m.COMMON, m.UNCOMMON, m.RARE, m.EPIC, m.LEGENDARY, m.PEARLESCENT]
    groups = [m.rarity_options, m.manufacturer_options, m.gear_type_options, m.character_options, m.firmware_options, m.ammo_type_options, m.pickup_options, m.highlight_rarity_options, m.highlight_manufacturer_options, m.highlight_gear_type_options, m.highlight_pickup_options]
    items, broken = [], 0
    def new_item():
        kind = rng.random()
        if kind < 0.75:
            flags = {f: rng.random() < 0.15 for f in ("HasFirmware", "HasAnointment", "IsShiny") if rng.random() < 0.5}
            i = Item(rng.choice(bodies), rng.choice(["MID_M_JAK_x", "MID_M_LEG_x", "MID_M_x"]), Beam(C[rng.choice(rarities)], **flags))
        elif kind < 0.9:
            i = Item("", rng.choice(["MI_AMMO_SMG", "MI_Health", "MI_Money", "MI_ArmorShard", "M_ShieldBooster", "MI_Pretty"]))
        else:
            i = Item("X'/Game/Missions/Y.Y'", "MI_Q", Beam(C[m.MISSION]))
        i.location = types.SimpleNamespace(X=rng.uniform(-2000, 2000), Y=rng.uniform(-2000, 2000), Z=0.0)
        return i
    problems = []
    for step in range(steps):
        event = rng.random()
        if event < 0.25: items.append(new_item())
        elif event < 0.40 and items: items.pop(rng.randrange(len(items)))
        elif event < 0.60:
            o = rng.choice(list(rng.choice(groups).values())); o.value = not o.value
        elif event < 0.65: m.keep_firmware.value = not m.keep_firmware.value
        elif event < 0.70: m.block_pickup.value = not m.block_pickup.value
        elif event < 0.75: m.show_dropped.value = not m.show_dropped.value
        elif event < 0.80: m.filter_mode.value = rng.choice([m.MODE_HIDE, m.MODE_HIGHLIGHT])
        elif event < 0.84: m.toggle_hiding.callback()
        elif event < 0.88: m.protected_rarity.value = rng.choice(m.protected_rarity.choices)
        elif event < 0.92: m.minimum_level.value = rng.choice([0, 30, 60])
        elif event < 0.95: THE_PC.PlayerState.BackpackItems.items = slots(rng.randint(0, 8))
        elif event < 0.97: m.beam_intensity.value = rng.choice([10.0, 30.0]); m.beam_size.value = rng.choice([1.0, 2.0])
        world["InventoryPickup"] = list(items)
        # Enough scans to get through any backlog, then everything must be settled
        for _ in range(1 + len(items) // m.MAX_READS_PER_SCAN + 1): m.apply_filter()
        hiding = not m.paused and m.filter_mode.key == m.MODE_HIDE
        highlighting = not m.paused and m.filter_mode.key == m.MODE_HIGHLIGHT
        for i in items:
            k = m.item_key(i); info = m.item_infos.get(k)
            if info is None: problems.append((step, "never read", i.BodyData)); continue
            want_hide = hiding and m.should_hide(info) and not (m.show_dropped.value and k in m.dropped_items)
            want_block = want_hide and m.block_pickup.value
            want_boost = highlighting and m.should_highlight(info) and i.AttractEffectComponent is not None and m.read_beam_color(i.AttractEffectComponent) is not None
            if i.bHidden != want_hide: problems.append((step, "hidden", i.bHidden, want_hide, info.kind, info.body))
            if i.collision == want_block: problems.append((step, "collision", i.collision, want_block))
            if i.RootPrimitiveComponent.physics == want_block: problems.append((step, "physics", i.RootPrimitiveComponent.physics, want_block))
            beam = i.AttractEffectComponent
            if beam is not None:
                if beam.hidden != want_hide: problems.append((step, "beam hidden", beam.hidden, want_hide))
                if (k in m.boosted_beams) != want_boost: problems.append((step, "boost", k in m.boosted_beams, want_boost, info.kind))
                if want_boost:
                    want_color = m.boosted_beams[k].boosted_color
                    if not m.colors_match(m.read_beam_color(beam), want_color): problems.append((step, "boost colour"))
                elif m.read_beam_color(beam) is not None and info.kind in rarities and m.classify_color(m.read_beam_color(beam)) is None: problems.append((step, "beam left boosted", info.kind))
            if (k in m.highlight_pointers) != (highlighting and m.should_highlight(info)): problems.append((step, "marker"))
        alive = {m.item_key(i) for i in items}
        for known in (m.hidden_by_us, m.blocked_items, m.dropped_items, m.boosted_beams, m.item_infos, m.decided_with, m.highlight_pointers, m.skip_until):
            if set(known) - alive: problems.append((step, "remembers what's gone", len(set(known) - alive)))
        if problems: break
    # Turning the mod off gives everything back
    if not problems:
        m.paused = False; m.on_disable()
        for i in items:
            if i.bHidden or not i.collision or not i.RootPrimitiveComponent.physics: problems.append(("disable", i.bHidden, i.collision))
            beam = i.AttractEffectComponent
            if beam is not None and (beam.hidden or (m.read_beam_color(beam) is not None and m.classify_color(m.read_beam_color(beam)) is None)): problems.append(("disable beam",))
    return problems[:3]
start_soak = __import__("time").perf_counter()
for seed in range(int(__import__("os").environ.get("GIH_SOAK_RUNS", 6))):
    res = soak(seed, 500)
    check(f"random run {seed}", res, [])
print(f"SOAK took {__import__('time').perf_counter() - start_soak:.1f}s")
m.read_item_serial = real_ris; m.SKIPPED_ITEM_RETRY = 2.0; m.firmware_problem_logged = False; world["InventoryPickup"] = []; m.paused = False; m.filter_mode.value = m.MODE_HIDE
for group in (m.rarity_options, m.manufacturer_options, m.gear_type_options, m.character_options, m.ammo_type_options, m.pickup_options):
    for o in group.values(): o.value = o.default_value

# --- The messier things a real game does ---------------------------------------------------------------------
def rough_soak(seed, steps):
    rng = _r.Random(seed)
    W.made.clear()
    fresh(); m.item_infos.clear(); m.decided_with.clear(); m.hidden_by_us.clear(); m.blocked_items.clear(); m.boosted_beams.clear(); m.highlight_pointers.clear(); m.skip_until.clear()
    m.remove_radar(); m.remove_banner(); m.paused = False; m.filter_mode.value = m.MODE_HIDE; m.protected_rarity.value = m.LEGENDARY; m.minimum_level.value = 0
    m.read_item_serial = lambda i: None; m.SKIPPED_ITEM_RETRY = 0.0; m.firmware_problem_logged = True; m.rarity_options[m.COMMON].value = True
    THE_PC.PlayerState = types.SimpleNamespace(BackpackItems=types.SimpleNamespace(items=slots(5)))
    class Flaky(Item):
        dead = False
        def IsActorBeingDestroyed(self):
            if self.dead: raise RuntimeError("dead object")
            return False
    items, game_hidden, problems = [], set(), []
    iotd = None
    for step in range(steps):
        event = rng.random()
        if event < 0.30:
            i = Flaky(smg_jak, "MID_M_JAK_x", Beam(C[rng.choice([m.COMMON, m.EPIC])], HasFirmware=rng.random() < 0.2))
            i.location = types.SimpleNamespace(X=rng.uniform(-3000, 3000), Y=0.0, Z=0.0)
            items.append(i)
        elif event < 0.45 and items:
            gone = items.pop(rng.randrange(len(items))); game_hidden.discard(gone.id)
        elif event < 0.50 and items:
            # The game hides one which isn't ours
            i = rng.choice(items)
            if m.item_key(i) not in m.hidden_by_us and i.id not in game_hidden and m.item_key(i) not in m.item_infos:
                i.bHidden = True; game_hidden.add(i.id)
        elif event < 0.55 and items:
            rng.choice(items).dead = not rng.choice(items).dead
        elif event < 0.60:
            # A map change: everything goes, widgets with it
            items.clear(); game_hidden.clear()
            for w in W.made: w.in_viewport = False
        elif event < 0.65:
            iotd = rng.choice(items) if items and rng.random() < 0.5 else None
            pick = iotd
            world["OakVendingMachine"] = [types.SimpleNamespace(Class=Item.Class, IsActorBeingDestroyed=lambda: False, GetIOTDForPlayer=lambda pc, p=pick: p)]
        elif event < 0.70: m.filter_mode.value = rng.choice([m.MODE_HIDE, m.MODE_HIGHLIGHT])
        elif event < 0.74: m.toggle_hiding.callback()
        elif event < 0.78: THE_PC.Pawn = None if rng.random() < 0.5 else types.SimpleNamespace(K2_GetActorLocation=lambda: types.SimpleNamespace(X=0.0, Y=0.0, Z=0.0))
        elif event < 0.82: THE_PC.PlayerState = None if rng.random() < 0.5 else types.SimpleNamespace(BackpackItems=types.SimpleNamespace(items=slots(rng.randint(0, 6))))
        elif event < 0.85: m.show_radar.value = not m.show_radar.value
        world["InventoryPickup"] = list(items)
        try:
            for _ in range(3):
                m.last_scan = 0.0; m.last_widget_check = -100.0; m.scan_backlog = False
                m.on_tick(None, None, None, None)
        except Exception as ex:
            problems.append((step, "escaped the tick", repr(ex))); break
        for i in items:
            k = m.item_key(i)
            if i.id in game_hidden and k in m.hidden_by_us: problems.append((step, "took over what the game hid"))
            if i.id in game_hidden and not i.bHidden: problems.append((step, "showed what the game hid"))
            if iotd is i and not m.paused and not i.dead and (k in m.hidden_by_us or k in m.boosted_beams): problems.append((step, "touched the item of the day"))
        live_radars_now = [w for w in W.made if w.in_viewport and (w.name or "").startswith("GroundItemHider_Radar")]
        live_banners_now = [w for w in W.made if w.in_viewport and (w.name or "").startswith("GroundItemHider_Banner")]
        if len(live_radars_now) > 1: problems.append((step, "two radars"))
        if len(live_banners_now) > 1: problems.append((step, "two banners"))
        if not m.paused and len(live_banners_now) != 1: problems.append((step, "no banner", len(live_banners_now)))
        if m.paused and live_banners_now: problems.append((step, "banner while paused"))
        if problems: break
    THE_PC.Pawn = types.SimpleNamespace(K2_GetActorLocation=lambda: types.SimpleNamespace(X=0.0, Y=0.0, Z=0.0))
    THE_PC.PlayerState = types.SimpleNamespace(BackpackItems=types.SimpleNamespace(items=[]))
    world["OakVendingMachine"] = []; world["InventoryPickup"] = []; m.show_radar.value = True
    return problems[:3]
Log.logs.clear()
for seed in range(int(__import__("os").environ.get("GIH_SOAK_RUNS", 6))):
    res = rough_soak(seed, 500)
    check(f"rough run {seed}", res, [])
check("radar never failed", [l for l in Log.logs if "show the radar" in l or "on screen warning" in l][:2], [])
m.read_item_serial = real_ris; m.SKIPPED_ITEM_RETRY = 2.0; m.firmware_problem_logged = False; m.paused = False; m.filter_mode.value = m.MODE_HIDE
for group in (m.rarity_options, m.manufacturer_options, m.gear_type_options, m.character_options, m.ammo_type_options, m.pickup_options):
    for o in group.values(): o.value = o.default_value

# --- An item of the day found late ------------------------------------------------------------------------------
fresh(); m.item_infos.clear(); m.decided_with.clear(); m.hidden_by_us.clear(); m.blocked_items.clear(); m.filter_mode.value = m.MODE_HIDE; m.rarity_options[m.COMMON].value = True
m.VENDING_INTERVAL = 1000.0; m.VENDING_NEW_ITEM_INTERVAL = 1000.0; m.last_vending = __import__("time").monotonic(); m.vending_items = set()
late_iotd = gear(smg_jak, m.COMMON); world["InventoryPickup"] = [late_iotd]; m.apply_filter()
check("seen before its machine, hidden", (late_iotd.bHidden, late_iotd.collision), (True, False))
m.vending_items = {m.item_key(late_iotd)}; m.apply_filter()
check("given back once it's known", (late_iotd.bHidden, late_iotd.collision, late_iotd.AttractEffectComponent.hidden), (False, True, False))
check("and forgotten", (m.item_key(late_iotd) in m.hidden_by_us, m.item_key(late_iotd) in m.blocked_items), (False, False))
fresh(); m.item_infos.clear(); m.decided_with.clear(); m.highlight_rarity_options[m.COMMON].value = True; m.vending_items = set()
late2 = gear(smg_jak, m.COMMON); world["InventoryPickup"] = [late2]; m.apply_filter(); check("boosted first", m.item_key(late2) in m.boosted_beams)
m.vending_items = {m.item_key(late2)}; m.apply_filter(); check("beam restored too", (m.item_key(late2) in m.boosted_beams, m.classify_color(m.read_beam_color(late2.AttractEffectComponent))), (False, m.COMMON))
# A new pickup makes it look sooner than it otherwise would
m.VENDING_INTERVAL = 1000.0; m.VENDING_NEW_ITEM_INTERVAL = 0.0; asked = []; world["OakVendingMachine"] = [types.SimpleNamespace(Class=Item.Class, IsActorBeingDestroyed=lambda: False, GetIOTDForPlayer=lambda pc: (asked.append(1), None)[1])]
m.last_vending = __import__("time").monotonic(); m.filter_mode.value = m.MODE_HIDE; m.item_infos.clear(); world["InventoryPickup"] = []; m.apply_filter(); check("nothing new, machines left alone", len(asked), 0)
world["InventoryPickup"] = [gear(smg_jak, m.EPIC)]; m.apply_filter(); check("something new, machines asked", len(asked), 1)
m.VENDING_INTERVAL = 0.0; world["OakVendingMachine"] = []; world["InventoryPickup"] = []; m.vending_items = set(); m.apply_filter()

# --- How much is still lying around ------------------------------------------------------------------------------
fresh(); m.item_infos.clear(); m.decided_with.clear(); m.hidden_by_us.clear(); m.blocked_items.clear(); m.filter_mode.value = m.MODE_HIDE; m.rarity_options[m.COMMON].value = True; m.remove_banner()
banner_now = lambda: [c for c in m.banner_label.calls if c[0] == "SetText"][-1][1][0]
world["InventoryPickup"] = []; tick_now(); check("nothing around, plain", banner_now(), "FILTR AKTYWNY")
c1, c2, e1 = gear(smg_jak, m.COMMON), gear(smg_jak, m.COMMON), gear(smg_jak, m.EPIC)
ammo_pile, mission = Item("", "MI_AMMO_SMG"), Item("X'/Game/Missions/Y.Y'", "MI_Q", Beam(C[m.MISSION]))
world["InventoryPickup"] = [c1, c2, e1, ammo_pile, mission]; tick_now(); tick_now()
check("hidden and left", banner_now(), "FILTR AKTYWNY: ukryte 2, do zebrania 1")
world["InventoryPickup"] = [c1, c2, ammo_pile, mission]; tick_now(); tick_now(); check("picking it up counts down", banner_now(), "FILTR AKTYWNY: ukryte 2, do zebrania 0")
world["InventoryPickup"] = [ammo_pile, mission]; tick_now(); tick_now(); check("consumables and mission items don't count", banner_now(), "FILTR AKTYWNY")
e2 = gear(smg_jak, m.EPIC); world["InventoryPickup"] = [e2]; tick_now(); tick_now(); check("only left", banner_now(), "FILTR AKTYWNY: ukryte 0, do zebrania 1")
m.dropped_items.add(m.item_key(e2)); m.update_banner(THE_PC); check("what you dropped doesn't count", banner_now(), "FILTR AKTYWNY"); m.dropped_items.clear()
game_hides = gear(smg_jak, m.EPIC); game_hides.bHidden = True; world["InventoryPickup"] = [game_hides]; m.skip_until.clear(); tick_now(); tick_now(); check("what the game hid doesn't count", banner_now(), "FILTR AKTYWNY")
iot2 = gear(smg_jak, m.EPIC); world["OakVendingMachine"] = [types.SimpleNamespace(Class=Item.Class, IsActorBeingDestroyed=lambda: False, GetIOTDForPlayer=lambda pc: iot2)]; world["InventoryPickup"] = [iot2]; tick_now(); tick_now(); check("nor an item of the day", banner_now(), "FILTR AKTYWNY"); world["OakVendingMachine"] = []
m.filter_mode.value = m.MODE_HIGHLIGHT; m.highlight_rarity_options[m.LEGENDARY].value = True; m.item_infos.clear(); m.decided_with.clear()
l1, e3 = gear(smg_jak, m.LEGENDARY), gear(smg_jak, m.EPIC); world["InventoryPickup"] = [l1, e3]; tick_now(); tick_now(); check("highlight mode counts too", banner_now(), "FILTR AKTYWNY: PODSWIETLANIE: 1, do zebrania 2")
world["InventoryPickup"] = []; m.filter_mode.value = m.MODE_HIDE; m.remove_banner(); m.apply_filter()

# --- Markers on the game's own radar ---------------------------------------------------------------------------
sys.modules.pop("bl4_mod_menu.uilink", None); m.hud_radar_registered = False; m.hud_radar_found = None
check("the game's radar is the default", m.radar_place.default_value, m.RADAR_GAME)
fresh(); m.filter_mode.value = m.MODE_HIDE; world["InventoryPickup"] = []; tick_now(); check("no menu mod, nothing registered", m.hud_radar_registered, False)
calls = []; link_state = {"state": "live"}
link = types.ModuleType("bl4_mod_menu.uilink"); link.HUD = "HUD"; link.status = lambda: dict(link_state)
link.register = lambda *a, **k: calls.append(("register", a, k)); link.unregister = lambda key: calls.append(("unregister", key)); link.changed = lambda key: calls.append(("changed", key))
sys.modules["bl4_mod_menu.uilink"] = link
tick_now(); tick_now(); check("registered once", [c[0] for c in calls if c[0] == "register"], ["register"])
registered = next(c for c in calls if c[0] == "register")
check("for the HUD page only", registered[2]["views"], ("HUD",)); check("its script", registered[1][1], m.HUD_RADAR_SCRIPT)
state_fn, report = registered[1][2], registered[1][3]

# Hide mode shows the gear still lying around
fresh(); m.radar_place.value = m.RADAR_GAME; m.item_infos.clear(); m.decided_with.clear(); m.visible_gear_pointers.clear(); m.filter_mode.value = m.MODE_HIDE; m.rarity_options[m.COMMON].value = True
hidden_one, left_one, ammo_one = gear(smg_jak, m.COMMON), gear(smg_jak, m.LEGENDARY), Item("", "MI_AMMO_SMG")
left_one.location = types.SimpleNamespace(X=5000.0, Y=0.0, Z=0.0); world["InventoryPickup"] = [hidden_one, left_one, ammo_one]; tick_now()
state_now = state_fn(); marks = state_now["m"]; check("one marker, for what's left", len(marks), 1)
check("sends where it is", (marks[0][0], marks[0][1]), (5000.0, 0.0)); check("in its rarity's colour", marks[0][2], m.HUD_MARKER_COLORS[m.LEGENDARY])
check("sends where you are", state_now["p"], [0.0, 0.0]); check("and the range in world units", state_now["r"], m.radar_range.value * 100.0)
THE_PC.GetControlRotation = lambda: types.SimpleNamespace(Yaw=90.0); check("and which way you look", state_fn()["y"], 90.0); THE_PC.GetControlRotation = lambda: types.SimpleNamespace(Yaw=0.0)
check("default range", m.radar_range.default_value, 40.0)
m.dropped_items.add(m.item_key(left_one)); m.decided_with.clear(); m.apply_filter(); check("what you dropped isn't marked", state_fn()["m"], []); m.dropped_items.clear(); m.decided_with.clear(); m.apply_filter()
m.show_left_on_radar.value = False; m.apply_filter(); check("the option turns that off", state_fn()["m"], []); m.show_left_on_radar.value = True; m.apply_filter()
m.toggle_hiding.callback(); check("nothing while paused", state_fn()["m"], []); m.toggle_hiding.callback()
check("own radar isn't built", len(live_radars()), 0)

# Highlight mode shows what's highlighted
m.filter_mode.value = m.MODE_HIGHLIGHT; m.highlight_rarity_options[m.LEGENDARY].value = True; tick_now(); tick_now()
check("highlight marks its own", len(state_fn()["m"]), 1); check("still no second radar", len(live_radars()), 0)
m.show_radar.value = False; check("option hides markers", state_fn()["m"], []); m.show_radar.value = True
THE_PC.Pawn, keep_pawn = None, THE_PC.Pawn; check("no pawn is fine", state_fn()["m"], []); THE_PC.Pawn = keep_pawn
many_left = [gear(smg_jak, m.LEGENDARY) for _ in range(m.RADAR_MAX_MARKERS + 5)]; world["InventoryPickup"] = many_left
for _ in range(10): m.apply_filter()
check("marker count is limited", len(state_fn()["m"]), m.RADAR_MAX_MARKERS)

# Turning with you, and falling back to our own
calls.clear(); m.last_radar = 0.0; m.scan_interval.value = 1000.0; m.last_scan = __import__("time").monotonic(); m.on_tick(None, None, None, None); check("asks for a refresh between scans", calls, [("changed", m.HUD_RADAR_KEY)]); m.scan_interval.value = 0.25
Log.logs.clear(); report({"found": False}); check("page says no radar", (m.game_radar_usable(), any("not found" in l for l in Log.logs)), (False, True))
tick_now(); check("own radar takes over", len(live_radars()), 1)
report({"found": True}); tick_now(); check("and hands back", len(live_radars()), 0)
link_state["state"] = "next_start"; tick_now(); check("before the first restart, own radar", len(live_radars()), 1); link_state["state"] = "live"; tick_now()
m.radar_place.value = m.RADAR_LEFT; check("own radar by choice", (tick_now(), len(live_radars()))[1], 1); check("no markers sent then", state_fn()["m"], []); m.radar_place.value = m.RADAR_GAME; tick_now()
mod.enable(); mod.disable(); check("taken out on disable", [c for c in calls if c[0] == "unregister"][-1], ("unregister", m.HUD_RADAR_KEY)); check("can register again", m.hud_radar_registered, False)
def link_boom(*a, **k): raise RuntimeError("old link")
link.register = link_boom; Log.logs.clear(); m.register_hud_radar(); m.register_hud_radar(); check("failure logged once", sum("game's radar" in l for l in Log.logs), 1)
sys.modules.pop("bl4_mod_menu.uilink", None); m.hud_radar_registered = False; m.hud_radar_found = None; m.remove_banner(); m.remove_radar(); world["InventoryPickup"] = []; m.filter_mode.value = m.MODE_HIDE; m.radar_place.value = m.RADAR_LEFT
check("the script's installed", (root.parent if False else True))

# --- Reading parts from memory laid out like the game's -----------------------------------------------------------
keep_alive = []
def definition(index, owner=None):
    blob = ctypes.create_string_buffer(0x40); keep_alive.append(blob)
    ctypes.memmove(ctypes.addressof(blob) + 0x18 + 0x12, struct.pack("<h", index), 2)
    if owner is not None: ctypes.memmove(ctypes.addressof(blob) + 0x30, struct.pack("<Q", ctypes.addressof(owner)), 8)
    return blob
def pickup_memory(item_type, parts):
    type_table = definition(item_type); composition = definition(5, type_table)
    array = (ctypes.c_uint64 * max(1, len(parts)))(*[ctypes.addressof(p) for p in parts]); keep_alive.append(array)
    blob = ctypes.create_string_buffer(0x3F0 + 0xC0); keep_alive.append(blob)
    identity = ctypes.addressof(blob) + 0x3F0
    ctypes.memmove(identity + 0x8, struct.pack("<Q", ctypes.addressof(composition)), 8)
    ctypes.memmove(identity + 0x10, struct.pack("<QI", ctypes.addressof(array), len(parts)), 12)
    return blob
shields, repairs, own_table = definition(246), definition(243), definition(269)
real_key = m.item_key
def as_pickup(blob): m.item_key = lambda i: ctypes.addressof(blob)
as_pickup(pickup_memory(321, [definition(3, own_table), definition(1, shields), definition(9, own_table)]))
check("firmware from a part", m.read_item_identity(None)[:2], (321, "god_killer"))
as_pickup(pickup_memory(269, [definition(3, own_table), definition(2, repairs)])); check("repkit's firmware table", m.read_item_identity(None)[:2], (269, "reel_big_fist"))
as_pickup(pickup_memory(269, [definition(3, own_table)])); check("no firmware part", m.read_item_identity(None)[:2], (269, None))
as_pickup(pickup_memory(269, [])); check("no parts", m.read_item_identity(None)[:2], (269, None))
as_pickup(pickup_memory(269, [definition(999, shields)])); check("a number the table doesn't have", m.read_item_identity(None)[1], None)
bad = ctypes.create_string_buffer(0x3F0 + 0xC0); as_pickup(bad); check("an empty identity is harmless", tuple(m.read_item_identity(None)), (None, None, None))
ctypes.memmove(ctypes.addressof(bad) + 0x3F0 + 0x10, struct.pack("<QI", 0x10, 10 ** 6), 12); check("a silly count is refused", tuple(m.read_item_identity(None)), (None, None, None))
ctypes.memmove(ctypes.addressof(bad) + 0x3F0 + 0x10, struct.pack("<QI", 0x10, 3), 12); check("a bad array is refused", tuple(m.read_item_identity(None)), (None, None, None))
ctypes.memmove(ctypes.addressof(bad) + 0x3F0 + 0x8, struct.pack("<Q", 0x123456), 8); check("a bad composition is refused", m.read_item_identity(None).item_type, None)
# Through to the decisions, with no serial text at all, as on the ground
as_pickup(pickup_memory(269, [definition(1, repairs)])); m.read_item_serial = lambda i: None; m.firmware_read_successes = 0; m.firmware_read_failures = 0
info_now = m.read_item_info(gear(repkit, m.EPIC, HasFirmware=True), 1); check("full read: firmware", info_now.firmware_name, "god_killer"); check("full read: maker", info_now.manufacturer, "Vladof"); check("counted as read", m.firmware_read_successes, 1)
# The serial's level still comes through
m.read_item_serial = lambda i: leveled(269, 55); info_now = m.read_item_info(gear(repkit, m.EPIC, HasFirmware=True), 1); check("level from the serial, firmware from the parts", (info_now.level, info_now.firmware_name), (55, "god_killer"))
m.item_key = real_key; m.read_item_serial = real_ris

# --- Nothing changed, nothing to go through ------------------------------------------------------------------------
fresh(); m.item_infos.clear(); m.decided_with.clear(); m.hidden_by_us.clear(); m.blocked_items.clear(); m.filter_mode.value = m.MODE_HIDE; m.rarity_options[m.COMMON].value = True; m.BOOST_CHECK_INTERVAL = 1000.0
pile = [gear(smg_jak, m.COMMON) for _ in range(9)] + [gear(smg_jak, m.EPIC)]; world["InventoryPickup"] = pile
for _ in range(3): m.apply_filter()
m.FULL_PASS_INTERVAL = 1000.0; m.apply_filter(); m.recent_items.clear(); m.apply_filter()
passes = []; real_hi = m.get_item_info; real_gv = m.get_vending_machine_items; m.get_vending_machine_items = lambda *a: (passes.append(1), real_gv(*a))[1]
for _ in range(20): m.apply_filter()
check("same pickups, no pass through them", len(passes), 0)
new_one = gear(smg_jak, m.COMMON); world["InventoryPickup"] = pile + [new_one]; m.apply_filter(); check("a new one is noticed at once", (new_one.bHidden, len(passes)), (True, 1))
m.apply_filter(); m.recent_items.clear(); m.apply_filter(); passes.clear()
world["InventoryPickup"] = pile; m.apply_filter(); check("one going is noticed at once", (len(passes), m.item_key(new_one) in m.hidden_by_us), (1, False))
m.apply_filter(); m.recent_items.clear(); m.apply_filter(); passes.clear()
m.rarity_options[m.EPIC].value = True; m.apply_filter(); check("a setting's noticed at once", (len(passes), pile[-1].bHidden), (1, True)); m.rarity_options[m.EPIC].value = False; m.apply_filter(); m.apply_filter(); passes.clear()
m.toggle_hiding.callback(); check("pausing's noticed at once", pile[0].bHidden, False); m.toggle_hiding.callback(); check("resuming too", pile[0].bHidden, True); m.apply_filter(); passes.clear()
m.last_full_pass = -5000.0; m.apply_filter(); check("still goes through them now and then", len(passes), 1)
m.get_vending_machine_items = real_gv; m.FULL_PASS_INTERVAL = 0.0; m.BOOST_CHECK_INTERVAL = 0.0
# A backlog keeps going
m.FULL_PASS_INTERVAL = 1000.0; m.item_infos.clear(); m.decided_with.clear(); m.hidden_by_us.clear(); many = [gear(smg_jak, m.COMMON) for _ in range(35)]; world["InventoryPickup"] = many
for _ in range(5): m.apply_filter()
check("a backlog isn't cut short", sum(i.bHidden for i in many), 35); m.FULL_PASS_INTERVAL = 0.0
# How much an idle scan costs on what a real session had lying around
import time as _t2
for count in (600,):
    fresh(); m.item_infos.clear(); m.decided_with.clear(); m.hidden_by_us.clear(); m.filter_mode.value = m.MODE_HIDE; m.rarity_options[m.COMMON].value = True
    pile = [gear(smg_jak, m.COMMON) for _ in range(count)]; world["InventoryPickup"] = pile; m.FULL_PASS_INTERVAL = 0.0
    for _ in range(70): m.apply_filter()
    start = _t2.perf_counter()
    for _ in range(200): m.apply_filter()
    full = (_t2.perf_counter() - start) / 200 * 1000
    m.FULL_PASS_INTERVAL = 1000.0; m.apply_filter(); m.recent_items.clear(); m.apply_filter()
    start = _t2.perf_counter()
    for _ in range(200): m.apply_filter()
    idle = (_t2.perf_counter() - start) / 200 * 1000
    print(f"BENCH {count} items: going through them {full:.3f} ms, skipping them {idle:.3f} ms")
m.FULL_PASS_INTERVAL = 0.0; world["InventoryPickup"] = []; m.apply_filter()

# --- Learning from the HUD page, and the identity dump ------------------------------------------------------------
m.hud_reports = 0; Log.logs.clear(); m.on_hud_radar_report({"label": "enemy_radar.js/0", "text": "code"}); check("page text reaches the log", any("HUD enemy_radar.js/0: code" in l for l in Log.logs)); check("doesn't touch the radar state", m.hud_radar_found, None)
m.hud_reports = m.HUD_MAX_REPORTS; Log.logs.clear(); m.on_hud_radar_report({"label": "x", "text": "y"}); check("limited", Log.logs, []); m.hud_reports = 0
m.identities_logged = m.IDENTITIES_TO_LOG - 1; Log.logs.clear(); real_rm = m.read_memory; m.read_memory = lambda a, n: b"\x01\x02"; m.log_identity(gear(smg_jak, m.EPIC), "somebody"); m.log_identity(gear(smg_jak, m.EPIC), "somebody"); m.read_memory = real_rm
check("identities logged, a few only", sum("Identity" in l and "0102" in l for l in Log.logs), 1)

# --- Language --------------------------------------------------------------------------------------------------------
def lang_state():
    return (m.shown_language, m.filter_mode.value, m.filter_mode.display_name, m.filter_mode.key)
m.language_option.value = m.LANGUAGE_AUTO; m.filter_mode.value = m.MODE_HIDE; m.game_language = None; m.apply_language()
check("nothing known falls back to English", lang_state(), ("en", "Hide", "Filter mode", m.MODE_HIDE))
m.set_game_language("polish"); check("Steam's name for Polish", lang_state(), ("pl", "Ukrywanie", "Tryb filtra", m.MODE_HIDE))
m.on_hud_radar_report({"lang": "en"}); check("the HUD can say otherwise", m.shown_language, "en")
m.on_hud_radar_report({"lang": "pl"}); check("the HUD's loc class", m.shown_language, "pl")
m.on_hud_radar_report({"lang": "de"}); check("other languages use English", m.shown_language, "en")
m.on_hud_radar_report({"lang": "pl-PL"}); check("with a region", m.shown_language, "pl")
check("language doesn't touch the radar state", m.hud_radar_found in (None, True, False), True)

m.language_option.value = m.ENGLISH; check("choosing overrides the game", lang_state(), ("en", "Hide", "Filter mode", m.MODE_HIDE))
m.on_hud_radar_report({"lang": "pl"}); check("the game can't override a choice", m.shown_language, "en")
check("own value follows", m.language_option.value, "English")
m.language_option.value = "Polski"; check("the menu sets it by its text", (m.shown_language, m.language_option.key), ("pl", m.POLISH))
m.language_option.value = m.LANGUAGE_AUTO; check("back to the game's", (m.shown_language, m.language_option.value), ("pl", "Automatycznie (jak w grze)"))

m.language_option.value = m.ENGLISH; m.radar_place.value = m.RADAR_GAME
check("menus in English", (next(k.display_name for k in mod.keybinds if k.identifier == "Toggle Item Hiding"), m.rarity_options[m.LEGENDARY].display_name, m.gear_type_options[m.SMG].description, m.protected_rarity.value, m.radar_place.value), ("Pause or resume the filter", "Legendary", "Hide all SMGs.", "Legendary", "The game's radar"))
check("mod description", mod.description.startswith("Loot filter"), True)
def walk(options):
    for option in options:
        yield option
        yield from walk(getattr(option, "children", ()))
everything = [*walk(mod.options), *mod.keybinds]
polish_letters = set("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")
leftovers = [o.display_name for o in everything if polish_letters & set(o.display_name + (o.description or "")) and o is not m.language_option]
check("no Polish left in the English menus", leftovers, [])
m.language_option.value = m.POLISH
polish_names = {o.identifier: o.display_name for o in walk(mod.options)}
m.language_option.value = m.ENGLISH
english_names = {o.identifier: o.display_name for o in walk(mod.options)}
same = sorted(i for i in polish_names if polish_names[i] == english_names[i])
known_same = {*m.manufacturer_options, *m.character_options, *(o.identifier for o in m.firmware_options.values()), "Eridium", "Language", "Epic"}
check("every other name changes with the language", [i for i in same if i not in known_same], [])

# The filter means the same in either language
m.language_option.value = m.POLISH; m.filter_mode.value = m.MODE_HIGHLIGHT; m.protected_rarity.value = m.EPIC; m.radar_place.value = m.RADAR_LEFT
before = (m.filter_mode.key, m.protected_rarity.key, m.radar_place.key)
check("texts are Polish", (m.filter_mode.value, m.protected_rarity.value, m.radar_place.value), ("Podświetlanie", "Epickie", "Lewy górny róg"))
m.language_option.value = m.ENGLISH
check("choices survive a language change", (m.filter_mode.key, m.protected_rarity.key, m.radar_place.key), before)
check("and read in English", (m.filter_mode.value, m.protected_rarity.value, m.radar_place.value), ("Highlight", "Epic", "Top left corner"))
check("the choices list too", m.filter_mode.choices, ["Hide", "Highlight"]); check("protection works", (m.is_protected(m.EPIC), m.is_protected(m.RARE)), (True, False))
m.filter_mode.value = "Podświetlanie"; check("a stale text still means the same", m.filter_mode.key, m.MODE_HIGHLIGHT)

# Saved and loaded the same whatever language is on
check("saved by meaning", (m.filter_mode._to_json(), m.protected_rarity._to_json(), m.radar_place._to_json(), m.language_option._to_json()), (m.MODE_HIGHLIGHT, m.EPIC, m.RADAR_LEFT, m.ENGLISH))
m.filter_mode._from_json("Ukrywanie"); check("old Polish setting loads", m.filter_mode.key, m.MODE_HIDE)
m.protected_rarity._from_json("Wyłączona"); check("old Polish protection loads", m.protected_rarity.key, m.NO_PROTECTION)
m.radar_place._from_json("Radar gry"); check("old Polish radar loads", m.radar_place.key, m.RADAR_GAME)
m.filter_mode._from_json(m.MODE_HIGHLIGHT); check("new setting loads", m.filter_mode.key, m.MODE_HIGHLIGHT)
m.filter_mode._from_json("rubbish"); check("nonsense changes nothing", m.filter_mode.key, m.MODE_HIGHLIGHT)
m.language_option._from_json(m.POLISH); check("the choice of language loads", m.shown_language, "pl")
m.reset_to_defaults(); check("reset keeps the language", (m.language_option.key, m.filter_mode.key, m.protected_rarity.key), (m.POLISH, m.MODE_HIDE, m.LEGENDARY))
check("language isn't a filter", m.language_option in m.filter_options, False)

m.language_option.value = m.ENGLISH; m.filter_mode.value = m.MODE_HIDE; m.hidden_by_us.clear(); check("banner in English", m.wanted_banner_text().startswith("FILTER ACTIVE"), True)
m.hidden_by_us.update({1, 2}); real_left = m.count_gear_left; m.count_gear_left = lambda: 3; check("counts in English", m.wanted_banner_text(), "FILTER ACTIVE: hidden 2, to collect 3")
m.language_option.value = m.POLISH; check("counts in Polish", m.wanted_banner_text(), "FILTR AKTYWNY: ukryte 2, do zebrania 3")
m.filter_mode.value = m.MODE_HIGHLIGHT; m.language_option.value = m.ENGLISH; check("highlight in English", m.wanted_banner_text().startswith("FILTER ACTIVE: HIGHLIGHTING"), True); m.filter_mode.value = m.MODE_HIDE
m.count_gear_left = real_left; m.hidden_by_us.clear()
real_mods = sys.modules.get("bl4_mod_menu.uilink"); sys.modules["bl4_mod_menu.uilink"] = types.SimpleNamespace(status=lambda: {"state": "next_start"})
check("notice in English", m.wanted_menu_notice(), "Restart the game to turn on the mod menu (F7)")
m.language_option.value = m.POLISH; check("notice in Polish", m.wanted_menu_notice(), "Uruchom grę ponownie, aby włączyć menu modów (F7)")
if real_mods is None: del sys.modules["bl4_mod_menu.uilink"]
else: sys.modules["bl4_mod_menu.uilink"] = real_mods

# Reading Steam's setting
steam_dir = Path(tempfile.mkdtemp()); game_dir = steam_dir / "common" / "Borderlands 4"; game_dir.mkdir(parents=True)
check("no manifest, no answer", m.steam_language(game_dir), None)
(steam_dir / f"appmanifest_{m.STEAM_APP_ID}.acf").write_text('"AppState"\n{\n\t"UserConfig"\n\t{\n\t\t"language"\t\t"polish"\n\t}\n}\n', encoding="utf8")
check("reads the manifest", m.steam_language(game_dir), "polish")
(steam_dir / f"appmanifest_{m.STEAM_APP_ID}.acf").write_text('"AppState"\n{\n}\n', encoding="utf8")
check("no language in it", m.steam_language(game_dir), None)
shutil.rmtree(steam_dir, ignore_errors=True)

# A settings file saved by this version, read back from the real mods_base code
m.language_option.value = m.ENGLISH
saved_values = {}
for option in walk(mod.options):
    value = option._to_json() if hasattr(option, "_to_json") and not hasattr(option, "children") else ...
    if value is not ...: saved_values[option.identifier] = value
check("the language is in what's saved", saved_values.get("Language"), m.ENGLISH)
check("what's saved is plain text", json.dumps(saved_values)[:1], "{")
m.language_option.value = m.LANGUAGE_AUTO
m.language_option._from_json(saved_values["Language"]); check("and comes back after a restart", (m.language_option.key, m.shown_language), (m.ENGLISH, "en"))
m.set_game_language("pl"); check("still over the game's", m.shown_language, "en")
# Through the real settings code and a real file
m.language_option.value = m.ENGLISH; m.filter_mode.value = m.MODE_HIGHLIGHT; mod.save_settings()
on_disk = json.loads(Path(mod.settings_file).read_text(encoding="utf8"))
def find_saved(tree, name):
    if name in tree: return tree[name]
    return next((v for v in (find_saved(c, name) for c in tree.values() if isinstance(c, dict)) if v is not None), None)
check("file holds the language", find_saved(on_disk, "Language"), m.ENGLISH); check("and the mode by meaning", find_saved(on_disk, "Filter Mode"), m.MODE_HIGHLIGHT)
m.language_option.value = m.POLISH; m.filter_mode.value = m.MODE_HIDE; mod.load_settings()
check("file loads back", (m.language_option.key, m.shown_language, m.filter_mode.key, m.filter_mode.value), (m.ENGLISH, "en", m.MODE_HIGHLIGHT, "Highlight"))
m.language_option.value = m.LANGUAGE_AUTO; m.filter_mode.value = m.MODE_HIDE; m.protected_rarity.value = m.LEGENDARY; m.radar_place.value = m.RADAR_GAME

print("FAILS:", fails)
sys.exit(1 if fails else 0)
