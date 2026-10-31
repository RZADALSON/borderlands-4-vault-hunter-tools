# Changelog

## 2.0.0

- The DPS meter is now part of this app, under `DPS meter` in its settings. Installing this removes the separate Borderlands 4 DPS Meter. The meter's settings go back to their defaults once.
- New name: Vault Hunter Tools, as it's more than a loot filter now.
- The meter counts each enemy as one kill, however many pellets hit it as it dies, and the last fight's line says how many there were.
- Items from chests disappear much sooner. A new item that wasn't ready yet could wait 1 to 3 seconds for its next check, now it's a tenth of a second.
- The banner looks like the panels on the game's HUD, and hides while a menu is open.
- Settings that don't do anything right now are greyed out, like the hide filters in highlight mode.
- Radar settings have their own page instead of sitting under highlighting. They go back to their defaults once.
- Removed `Hide below level`, which never worked as gear on the ground doesn't say its level, and the scan interval setting.

## 1.5.0

- New name: Borderlands 4 Loot Filter, was Ground Item Hider. Installing replaces the old version and keeps your settings.
- English menus, on-screen text and installer. The mod follows the game's language unless you pick one, and your pick is saved.
- The installer comes in two languages, `-PL` and `-EN`.

## 1.4.1

- Markers on the game's radar are drawn every frame, predicting movement between readings.
- Default radar range is 40 m instead of 100 m, markers sat too close to the middle.

## 1.4.0

- Item markers on the game's own radar, in rarity colours. When hiding, they show gear that's still lying around.
- The banner also says how much gear is left to pick up.
- Hidden items can't be picked up, as their collision gets turned off. There's an option for it.
- Items you drop from your backpack stay visible. They're spotted by the backpack shrinking and an item turning up next to you.
- Level filter.
- Ammo filter by weapon, and armor shards among the pickups.
- Manufacturer, type and character are read from the item's parts, which also works for legendary repair kits and enhancements.
- Select all and select none buttons on long lists, and a button to reset the filters.
- Messages in game when a patch or another mod stops the mod menu.
- Scan stats every 5 minutes in `unrealsdk.log`.
- Fixed BL4 Mod Menu's scrollbar showing with nothing to scroll.
- Uninstalling no longer leaves an empty `keybinds` folder, and the installed apps entry has an icon and a link.

## 1.3.0

- Class mod filter by character, and a choice of firmware sets.
- Faster scans, with a time limit.
- New banner with a count, and a radar in rarity colours next to the game's.
- A message about restarting after the first install.

## 1.1.1

- Fixed the installer failing on every computer in 1.1.0.
