"""
Our changes to BL4 Mod Menu, applied to its .sdkmod while building the installer.

The game's scrollbar only measures the column once, two frames after a page is drawn. If the page
is still being laid out by then, or a longer page was showing before, the bar keeps the wrong size,
and it shows even if there's nothing to scroll. This measures it a few more times, and hides the bar
if everything fits.

The menu can also only hide an option, not show that it does nothing right now. An option with a
`greyed_when` function now goes grey and can't be changed while that returns true.
"""

import sys
import zipfile
from pathlib import Path

CHANGES = {
    "bl4_mod_menu/ui/menu.js": [
        (
            """                ui.scrollbarQueued = false;
                if (!alive() || !ui.options) return;
                try {
                    ui.options.dispatchEvent(new CustomEvent("oakscrollupdate"));
                } catch (err) {}
            });
        });
    }
""",
            """                ui.scrollbarQueued = false;
                syncScrollbar();
                // The page can still be settling this soon after drawing it
                clearTimeout(ui.scrollbarLater);
                clearTimeout(ui.scrollbarLatest);
                ui.scrollbarLater = setTimeout(syncScrollbar, 120);
                ui.scrollbarLatest = setTimeout(syncScrollbar, 400);
            });
        });
    }

    // Measures the column again, and hides the bar if there's nothing to scroll
    function syncScrollbar() {
        if (!alive() || !ui.options) return;
        try {
            ui.options.dispatchEvent(new CustomEvent("oakscrollupdate"));
            var fits = ui.options.scrollHeight <= ui.options.clientHeight + 2;
            if (fits) ui.options.scrollTop = 0;
            var bar = ui.options.parentNode.querySelector(".oakscroll-v");
            if (bar) bar.style.display = fits ? "none" : "";
        } catch (err) {}
    }
""",
        ),
        (
            """        var comp = q(wrap, ".menu_options_entry_component") || wrap;
        entry.addEventListener("mouseenter", function () {
""",
            """        var comp = q(wrap, ".menu_options_entry_component") || wrap;
        if (node.greyed) entry.classList.add("bl4mm_greyed");
        entry.addEventListener("mouseenter", function () {
""",
        ),
        (
            """        if (node.changed && node.kind !== "keybind") {
""",
            """        if (node.changed && !node.greyed && node.kind !== "keybind") {
""",
        ),
    ],
    "bl4_mod_menu/ui/menu.css": [
        (
            """.bl4mm_disabled {
""",
            """.bl4mm_greyed {
    opacity: 0.35;
}

.bl4mm_greyed .menu_options_entry_component {
    pointer-events: none;
}

.bl4mm_disabled {
""",
        ),
    ],
    "bl4_mod_menu/model.py": [
        (
            """def option_json(option: BaseOption) -> dict[str, Any] | None:
    if not visible(option):
        return None
""",
            """def greyed(option: BaseOption) -> bool:
    check = getattr(option, "greyed_when", None)
    return check is not None and bool(check())


def option_json(option: BaseOption) -> dict[str, Any] | None:
    if not visible(option):
        return None
""",
        ),
        (
            """        "desc": plain(option.description),
    }
    match option:
""",
            """        "desc": plain(option.description),
        "greyed": greyed(option),
    }
    match option:
""",
        ),
        (
            """    \"\"\"Applies a value sent by the HTML menu, checked and converted for the option's type.\"\"\"
    match option:
""",
            """    \"\"\"Applies a value sent by the HTML menu, checked and converted for the option's type.\"\"\"
    if greyed(option):
        return
    match option:
""",
        ),
    ],
}


def patch_text(name: str, text: str) -> str:
    """Applies the changes to one file. Stops the build if the menu's code isn't what this was made for."""
    text = text.replace("\r\n", "\n")
    for old, new in CHANGES[name]:
        if text.count(old) != 1:
            raise ValueError(f"{name} changed, patch_menu.py needs another look")
        text = text.replace(old, new)
    return text


def patch_sdkmod(source: Path, target: Path) -> None:
    """Writes a copy of the .sdkmod with the changes in it."""
    with zipfile.ZipFile(source) as old, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as new:
        for entry in old.infolist():
            data = old.read(entry.filename)
            if entry.filename in CHANGES:
                data = patch_text(entry.filename, data.decode("utf-8")).encode("utf-8")
            new.writestr(entry, data)


if __name__ == "__main__":
    patch_sdkmod(Path(sys.argv[1]), Path(sys.argv[2]))
