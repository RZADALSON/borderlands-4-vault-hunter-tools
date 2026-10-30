"""
Builds the installer into installer/dist. Run it from anywhere: python installer/build.py

Needs vendor/: oak2-sdk.zip, bl4_mod_menu.sdkmod, vc_redist.x64.exe and the licence texts.
Needs tools/wix: dotnet tool install wix --tool-path tools --version 5.0.2
"""

import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

VERSION = "1.1.0"
VCREDIST_MINOR = "50"  # The oldest Visual C++ runtime which doesn't get replaced

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
VENDOR = HERE / "vendor"
BUILD = HERE / "build"
DIST = HERE / "dist"
PAYLOAD = BUILD / "payload"


def package_mod() -> Path:
    """Packs the filter the way the SDK wants it: one root folder, named after the file."""
    target = ROOT / "GroundItemHider.sdkmod"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as sdkmod:
        for name in ("__init__.py", "pyproject.toml"):
            sdkmod.write(ROOT / "GroundItemHider" / name, f"GroundItemHider/{name}")
    return target


def make_payload() -> None:
    """Lays out exactly what goes in the game's folder."""
    with zipfile.ZipFile(VENDOR / "oak2-sdk.zip") as sdk:
        sdk.extractall(PAYLOAD)

    mods = PAYLOAD / "sdk_mods"
    shutil.copy(package_mod(), mods / "GroundItemHider.sdkmod")
    shutil.copy(VENDOR / "bl4_mod_menu.sdkmod", mods / "bl4_mod_menu.sdkmod")

    # Dot folders aren't loaded as mods
    licenses = mods / ".licenses"
    licenses.mkdir()
    shutil.copy(HERE / "src" / "PRZECZYTAJ.txt", licenses / "PRZECZYTAJ.txt")
    shutil.copy(VENDOR / "GPL-3.0.txt", licenses / "GPL-3.0.txt")
    shutil.copy(VENDOR / "LGPL-3.0.txt", licenses / "LGPL-3.0.txt")
    shutil.copy(VENDOR / "Python-LICENSE.txt", licenses / "Python-LICENSE.txt")

    settings = BUILD / "GroundItemHider.json"
    settings.write_text('{"enabled": true}\n', encoding="utf8")


def make_bitmaps() -> tuple[Path, Path]:
    """Draws the dialogs' art. No game art, only the mod's own colours."""
    dark = (14, 22, 31)
    orange = (247, 130, 30)
    white = (255, 255, 255)

    banner = Image.new("RGB", (493, 58), white)
    draw = ImageDraw.Draw(banner)
    draw.rectangle((0, 55, 493, 58), fill=orange)
    draw.polygon(((493, 0), (440, 0), (405, 55), (493, 55)), fill=dark)
    draw.polygon(((440, 0), (432, 0), (397, 55), (405, 55)), fill=orange)
    banner_path = BUILD / "banner.bmp"
    banner.save(banner_path)

    # The left 164 pixels are what shows beside the welcome text, the rest stays white
    dialog = Image.new("RGB", (493, 312), white)
    draw = ImageDraw.Draw(dialog)
    draw.rectangle((0, 0, 163, 312), fill=dark)
    draw.rectangle((160, 0, 163, 312), fill=orange)
    for top, width in ((62, 110), (102, 80), (142, 50)):
        left = 82 - width // 2
        draw.polygon(((left, top), (left + width, top), (82 + width // 6, top + 26), (82 - width // 6, top + 26)), fill=orange)
    draw.rectangle((78, 182, 86, 250), fill=orange)
    dialog_path = BUILD / "dialog.bmp"
    dialog.save(dialog_path)
    return banner_path, dialog_path


def build_custom_actions() -> Path:
    subprocess.run(
        ["dotnet", "build", str(HERE / "ca" / "GameFolderActions.csproj"), "-c", "Release", "-v", "quiet", "-nologo"],
        check=True,
    )
    return HERE / "ca" / "bin" / "Release" / "net472" / "GameFolderActions.CA.dll"


def main() -> None:
    shutil.rmtree(BUILD, ignore_errors=True)
    BUILD.mkdir()
    DIST.mkdir(exist_ok=True)

    make_payload()
    banner, dialog = make_bitmaps()
    ca = build_custom_actions()

    msi = DIST / f"GroundItemHider-Setup-{VERSION}.msi"
    env = {**os.environ, "DOTNET_ROLL_FORWARD": "Major"}
    # Everything from short paths: WiX can't start its own helpers from this workspace's long one
    with tempfile.TemporaryDirectory(prefix="gih") as short:
        link = Path(short) / "p"
        shutil.copytree(PAYLOAD, link)
        tools = Path(short) / "t"
        shutil.copytree(HERE / "tools", tools)
        subprocess.run(
            [
                str(tools / "wix"), "build",
                str(HERE / "src" / "Package.wxs"),
                "-intermediatefolder", str(Path(short) / "i"),
                "-cabcache", str(Path(short) / "c"),
                "-loc", str(HERE / "src" / "Strings.pl-PL.wxl"),
                "-culture", "pl-PL",
                "-arch", "x64",
                "-ext", "WixToolset.UI.wixext/5.0.2",
                "-d", f"ProductVersion={VERSION}",
                "-d", f"VcRedistMinor={VCREDIST_MINOR}",
                "-d", f"PayloadDir={link}",
                "-d", f"SettingsFile={BUILD / 'GroundItemHider.json'}",
                "-d", f"CaDll={ca}",
                "-d", f"VcRedistExe={VENDOR / 'vc_redist.x64.exe'}",
                "-d", f"BannerBmp={banner}",
                "-d", f"DialogBmp={dialog}",
                "-o", str(msi),
            ],
            check=True,
            env=env,
        )
    print(msi, msi.stat().st_size)


if __name__ == "__main__":
    main()
