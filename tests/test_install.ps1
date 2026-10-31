# Installs and removes the MSI on a fake game folder. Never touches the real game.
param([string]$Msi, [string]$Out, [string]$OldMsi, [string]$NewMod)
$ErrorActionPreference = 'Continue'
$base = Join-Path $env:TEMP 'gih_test'
$fake = Join-Path $base 'Borderlands 4'
$empty = Join-Path $base 'empty'
$real = 'C:\Program Files (x86)\Steam\steamapps\common\Borderlands 4'
$lines = New-Object System.Collections.ArrayList
function Say($t) { [void]$lines.Add($t); $lines | Set-Content -Encoding UTF8 $Out }
function Check($name, $ok) { Say(("{0} {1}" -f $(if ($ok) { 'ok  ' } else { 'FAIL' }), $name)) }
function Run($arguments) { (Start-Process msiexec -ArgumentList $arguments -Wait -PassThru).ExitCode }
function RealHash { (Get-ChildItem -LiteralPath "$real\sdk_mods" -Recurse -File -Filter '*.sdkmod' | Get-FileHash | ForEach-Object Hash) -join ',' }

try {
    Remove-Item -LiteralPath $base -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force "$fake\OakGame\Binaries\Win64", $empty | Out-Null
    Set-Content -LiteralPath "$fake\Borderlands4.exe" 'fake'
    $before = RealHash
    $running = @(Get-Process Borderlands4 -ErrorAction SilentlyContinue).Count
    Say("game running: $running")

    $code = Run "/i `"$Msi`" /qn INSTALLFOLDER=`"$empty\`" /l*v `"$base\wrong.log`""
    Check "wrong folder refused (exit $code)" ($code -eq 1603)
    Check 'wrong folder got nothing' (-not (Test-Path "$empty\sdk_mods"))

    $code = Run "/i `"$Msi`" /qn INSTALLFOLDER=`"$fake\`" VCREDIST_MINOR=99 /l*v `"$base\install.log`""
    Check "install (exit $code)" ($code -eq 0)
    foreach ($f in 'OakGame\Binaries\Win64\dsound.dll', 'OakGame\Binaries\Win64\Plugins\unrealsdk.dll', 'OakGame\Binaries\Win64\Plugins\unrealsdk.toml', 'sdk_mods\__main__.py', 'sdk_mods\mods_base.sdkmod', 'sdk_mods\console_mod_menu.sdkmod', 'sdk_mods\keybinds\keybinds.pyd', 'sdk_mods\GroundItemHider.sdkmod', 'sdk_mods\bl4_mod_menu.sdkmod', 'sdk_mods\.licenses\PRZECZYTAJ.txt', 'sdk_mods\.licenses\GPL-3.0.txt', 'OakGame\Content\uiresources\bl4groundhider\hud_radar.js') {
        Check "installed $f" (Test-Path -LiteralPath "$fake\$f")
    }
    Check 'settings enable the filter' ((Get-Content -LiteralPath "$fake\sdk_mods\settings\GroundItemHider.json" -Raw) -match '"enabled": true')
    Check 'nothing in the default folder' (-not (Test-Path 'C:\Program Files\Borderlands 4'))
    $saved = (Get-ItemProperty 'HKLM:\Software\GroundItemHider' -ErrorAction SilentlyContinue).InstallFolder
    Check "folder remembered ($saved)" ($saved -eq "$fake\")
    $log = Get-Content -LiteralPath "$base\install.log" -Raw
    Check 'runtime installer ran from the msi' ($log -match "runtime's installer returned")
    Say(([regex]::Match($log, "runtime's installer returned \d+").Value))
    Say(("detect: " + [regex]::Match($log, 'Found the game in [^\r\n]*').Value))

    # What playing leaves behind, plus things that aren't ours
    New-Item -ItemType Directory -Force "$fake\OakGame\Content\Paks\~mods", "$fake\OakGame\Content\uiresources\bl4link", "$fake\OakGame\Content\uiresources\bl4modmenu", "$fake\sdk_mods\keybinds\__pycache__" | Out-Null
    Set-Content -LiteralPath "$fake\OakGame\Content\Paks\~mods\BL4Fix_UILink_4251_P.pak" 'x'
    Set-Content -LiteralPath "$fake\OakGame\Content\Paks\~mods\SomeoneElse_P.pak" 'keep'
    Set-Content -LiteralPath "$fake\OakGame\Content\uiresources\bl4link\boot.js" 'x'
    Set-Content -LiteralPath "$fake\OakGame\Content\uiresources\bl4modmenu\menu.js" 'x'
    Set-Content -LiteralPath "$fake\OakGame\Binaries\Win64\Plugins\unrealsdk.log" 'x'
    Set-Content -LiteralPath "$fake\sdk_mods\keybinds\__pycache__\a.pyc" 'x'
    Set-Content -LiteralPath "$fake\sdk_mods\OtherMod.sdkmod" 'keep'
    Set-Content -LiteralPath "$fake\sdk_mods\settings\GroundItemHider.json" '{"enabled": false, "mine": 1}'

    # Reinstalling over it keeps the player's settings
    $code = Run "/fa `"$Msi`" /qn /l*v `"$base\repair.log`""
    Check "repair (exit $code)" ($code -eq 0)
    Check 'repair keeps my settings' ((Get-Content -LiteralPath "$fake\sdk_mods\settings\GroundItemHider.json" -Raw) -match '"mine": 1')

    $code = Run "/x `"$Msi`" /qn /l*v `"$base\remove.log`""
    Check "uninstall (exit $code)" ($code -eq 0)
    foreach ($f in 'OakGame\Binaries\Win64\dsound.dll', 'OakGame\Binaries\Win64\Plugins\unrealsdk.dll', 'OakGame\Binaries\Win64\Plugins\unrealsdk.log', 'sdk_mods\__main__.py', 'sdk_mods\GroundItemHider.sdkmod', 'sdk_mods\bl4_mod_menu.sdkmod', 'sdk_mods\keybinds', 'sdk_mods\.licenses', 'OakGame\Content\Paks\~mods\BL4Fix_UILink_4251_P.pak', 'OakGame\Content\uiresources\bl4link', 'OakGame\Content\uiresources\bl4modmenu') {
        Check "removed $f" (-not (Test-Path -LiteralPath "$fake\$f"))
    }
    foreach ($f in 'Borderlands4.exe', 'OakGame\Content\Paks\~mods\SomeoneElse_P.pak', 'sdk_mods\OtherMod.sdkmod', 'sdk_mods\settings\GroundItemHider.json') {
        Check "kept $f" (Test-Path -LiteralPath "$fake\$f")
    }
    Check 'registry cleaned' (-not (Test-Path 'HKLM:\Software\GroundItemHider'))
    Check 'real game untouched' ($before -eq (RealHash))
    Say('left: ' + ((Get-ChildItem -LiteralPath $fake -Recurse -File | ForEach-Object { $_.FullName.Substring($fake.Length + 1) }) -join '; '))
    Say('empty folders left: ' + ((Get-ChildItem -LiteralPath $fake -Recurse -Directory | Where-Object { -not (Get-ChildItem -LiteralPath $_.FullName -Force) } | ForEach-Object { $_.FullName.Substring($fake.Length + 1) }) -join '; '))

    # --- Replacing what's already there ---
    if ($OldMsi) {
        $wanted = (Get-FileHash -LiteralPath $NewMod).Hash

        # Files someone copied in by hand, or left by an earlier install of any kind
        Remove-Item -LiteralPath $fake -Recurse -Force -ErrorAction SilentlyContinue
        New-Item -ItemType Directory -Force "$fake\OakGame\Binaries\Win64", "$fake\sdk_mods\settings" | Out-Null
        Set-Content -LiteralPath "$fake\Borderlands4.exe" 'fake'
        Set-Content -LiteralPath "$fake\sdk_mods\GroundItemHider.sdkmod" 'old'
        Set-Content -LiteralPath "$fake\sdk_mods\bl4_mod_menu.sdkmod" 'old'
        Set-Content -LiteralPath "$fake\OakGame\Binaries\Win64\dsound.dll" 'old'
        Set-Content -LiteralPath "$fake\sdk_mods\settings\GroundItemHider.json" '{"enabled": false, "mine": 1}'
        $code = Run "/i `"$Msi`" /qn INSTALLFOLDER=`"$fake\`" /l*v `"$base\manual.log`""
        Check "install over hand-copied files (exit $code)" ($code -eq 0)
        Check 'replaced the old filter' ((Get-FileHash -LiteralPath "$fake\sdk_mods\GroundItemHider.sdkmod").Hash -eq $wanted)
        Check 'replaced the old menu' ((Get-Content -LiteralPath "$fake\sdk_mods\bl4_mod_menu.sdkmod" -Raw -ErrorAction SilentlyContinue) -notmatch '^old')
        Check 'replaced the old dsound.dll' ((Get-Item -LiteralPath "$fake\OakGame\Binaries\Win64\dsound.dll").Length -gt 1000)
        Check 'kept settings over hand-copied files' ((Get-Content -LiteralPath "$fake\sdk_mods\settings\GroundItemHider.json" -Raw) -match '"mine": 1')
        $code = Run "/x `"$Msi`" /qn /l*v `"$base\manual_remove.log`""
        Check "remove after that (exit $code)" ($code -eq 0)

        # Updating from the previous installer, without saying where the game is
        Remove-Item -LiteralPath $fake -Recurse -Force -ErrorAction SilentlyContinue
        New-Item -ItemType Directory -Force "$fake\OakGame\Binaries\Win64" | Out-Null
        Set-Content -LiteralPath "$fake\Borderlands4.exe" 'fake'
        $code = Run "/i `"$OldMsi`" /qn INSTALLFOLDER=`"$fake\`" /l*v `"$base\old.log`""
        Check "install the old version (exit $code)" ($code -eq 0)
        $oldHash = (Get-FileHash -LiteralPath "$fake\sdk_mods\GroundItemHider.sdkmod").Hash
        Check 'old version is different' ($oldHash -ne $wanted)
        Set-Content -LiteralPath "$fake\sdk_mods\settings\GroundItemHider.json" '{"enabled": false, "mine": 2}'
        Set-Content -LiteralPath "$fake\sdk_mods\OtherMod.sdkmod" 'keep'
        $code = Run "/i `"$Msi`" /qn /l*v `"$base\upgrade.log`""
        Check "update over it (exit $code)" ($code -eq 0)
        Check 'update replaced the filter' ((Get-FileHash -LiteralPath "$fake\sdk_mods\GroundItemHider.sdkmod").Hash -eq $wanted)
        Check 'update found the same folder' ((Get-ItemProperty 'HKLM:\Software\GroundItemHider').InstallFolder -eq "$fake\")
        Check 'update kept settings' ((Get-Content -LiteralPath "$fake\sdk_mods\settings\GroundItemHider.json" -Raw) -match '"mine": 2')
        Check 'update kept other mods' (Test-Path -LiteralPath "$fake\sdk_mods\OtherMod.sdkmod")
        Check 'update kept SDK files' (Test-Path -LiteralPath "$fake\OakGame\Binaries\Win64\Plugins\unrealsdk.dll")
        $entries = @(Get-ChildItem 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall' | ForEach-Object { Get-ItemProperty $_.PSPath } | Where-Object { $_.DisplayName -like 'Borderlands 4 Loot Filter*' })
        Check "only one entry in installed apps ($($entries.Count)), version $($entries[0].DisplayVersion)" ($entries.Count -eq 1)
        $code = Run "/x `"$Msi`" /qn /l*v `"$base\final_remove.log`""
        Check "final uninstall (exit $code)" ($code -eq 0)
        Check 'final uninstall left no SDK' (-not (Test-Path -LiteralPath "$fake\OakGame\Binaries\Win64\dsound.dll"))
        Check 'final uninstall cleaned the registry' (-not (Test-Path 'HKLM:\Software\GroundItemHider'))
        Check 'real game still untouched' ($before -eq (RealHash))
    }
}
catch { Say("FAIL exception: $_") }
Say('DONE')
