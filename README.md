# Borderlands 4 Loot Filter

A loot filter for Borderlands 4. It hides the items you don't care about, or leaves everything on the ground and makes the ones you want stand out. Comes with an installer, so you don't need to set up the Python SDK yourself.

[Polski opis](README.pl.md)

## Install

1. Get `Borderlands4LootFilter-Setup-*-EN.msi` from [Releases](../../releases). There's a `-PL` one too, the only difference is the installer's language.
2. Close the game and run it. Check the game folder it found, or point it at the one with `Borderlands4.exe` in it.
3. Start the game. The first start prepares the mod menu, and a message in the top right asks you to restart.
4. Start it again. F7, or MODS in the pause menu, opens the settings.

Windows SmartScreen may warn you, because the installer isn't signed. The SHA-256 of each file is in the release notes.

It adds the Python SDK, the filter and BL4 Mod Menu to the game's folder, and the Microsoft Visual C++ Redistributable to Windows if it's missing. It doesn't touch your saves or replace any game files. If you already have an older version, it gets replaced and your settings stay.

BL4 Mod Menu checks GitHub for mod updates when the game starts, but doesn't download anything until you click. You can turn that off in its options.

## What it does

- **Hide mode:** chosen items disappear from the ground. Nothing gets deleted, turn the filter off and they're back. You can filter by rarity, manufacturer, item type and character (for class mods), and hide ammo by weapon, health and other pickups.
- **Highlight mode:** everything drops as usual, and the items you chose get a much stronger beam and a marker on the radar.
- **Radar markers** on the game's own radar, in rarity colours. In hide mode they show gear that's still lying around.
- **Firmware:** you choose which of the 24 sets always stay visible, or get highlighted.
- **Banner** in the top right while the filter is on, with how many items are hidden and how much gear is left to pick up.

Hidden items can't be picked up, and whatever you drop from your backpack stays visible. Both can be turned off.

White, green and blue items are hidden by default. Gear with firmware, an anointment or the shiny effect always stays visible unless you change that.

F8 pauses the filter. The menus are in Polish or English, following the language the game runs in. If you pick one under `Język / Language`, that's saved.

## Questions

**F7 opens a basic panel, or the game asks for a restart.** That's normal after installing, as the game only loads the menu's files when it starts. Restart it.

**I dropped an item and it vanished.** Drops are spotted by your backpack shrinking and an item turning up next to you, so something you throw down from your equipped gear may not be caught. F8 shows everything.

**Why can I see an item that should be hidden?** Usually one of the exceptions: firmware, anointment, shiny or rarity protection. You can turn them off.

**A game patch broke something.** The log is in `OakGame\Binaries\Win64\Plugins\unrealsdk.log`. The SDK may need a new version after a patch. If the game won't start, uninstall this or delete `OakGame\Binaries\Win64\dsound.dll`.

## Uninstall

Windows Settings, Installed apps, Borderlands 4 Loot Filter. Your mod settings and any mods you added yourself stay in `sdk_mods`.

## Building it

You need Python with Pillow, the .NET SDK and the .NET Framework 4.7.2 Targeting Pack.

```bash
dotnet tool install wix --tool-path installer/tools --version 5.0.2
python installer/build.py
```

`installer/vendor/` needs these first, they aren't in the repo:

| File | From |
|---|---|
| `oak2-sdk.zip` | [oak2-mod-manager v0.3](https://github.com/bl-sdk/oak2-mod-manager/releases/tag/v0.3) |
| `bl4_mod_menu.sdkmod` | [bl4-fix v2026.10.29.1](https://github.com/flameaway/bl4-fix/releases/tag/v2026.10.29.1) |
| `vc_redist.x64.exe` | [Microsoft](https://aka.ms/vs/17/release/vc_redist.x64.exe) |
| `GPL-3.0.txt`, `LGPL-3.0.txt`, `Python-LICENSE.txt`, `bl4-LICENSE.txt` | licence texts |

## Credits

The code here is [GPL-3.0](LICENSE). The installer also carries:

- [Oak2 Mod Manager](https://github.com/bl-sdk/oak2-mod-manager), [unrealsdk](https://github.com/bl-sdk/unrealsdk) and [pyunrealsdk](https://github.com/bl-sdk/pyunrealsdk) by bl-sdk, LGPL-3.0
- [BL4 Mod Menu](https://github.com/flameaway/bl4-fix) by flameaway, GPL-3.0, with a scrollbar fix
- Python, PSF licence
- Microsoft Visual C++ Redistributable, Microsoft's terms

Reading rarity from the beam is adapted from [BL4 Loot Filter](https://github.com/jlangowells/bl4_loot_filter) by Lango (GPL-3.0), who credits SlippyCheeze for the original logic. Colour palettes and item paths were checked against [Loot Magnet](https://github.com/max0n4ik/LootMagnet). The on-screen widgets follow [bl4-fix](https://github.com/flameaway/bl4-fix). The firmware parts table comes from [bl4](https://github.com/monokrome/bl4) by monokrome (BSD-2-Clause).

Not affiliated with Gearbox or 2K. No warranty.
