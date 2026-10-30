"""
Our change to BL4 Mod Menu, applied to its .sdkmod while building the installer.

The game's scrollbar only measures the column once, two frames after a page is drawn. If the page
is still being laid out by then, or a longer page was showing before, the bar keeps the wrong size,
and it shows even if there's nothing to scroll. This measures it a few more times, and hides the bar
if everything fits.
"""

import sys
import zipfile
from pathlib import Path

MENU_JS = "bl4_mod_menu/ui/menu.js"

OLD = """                ui.scrollbarQueued = false;
                if (!alive() || !ui.options) return;
                try {
                    ui.options.dispatchEvent(new CustomEvent("oakscrollupdate"));
                } catch (err) {}
            });
        });
    }
"""

NEW = """                ui.scrollbarQueued = false;
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
"""


def patch_text(text: str) -> str:
    """Applies the change. Stops the build if the menu's code isn't what this was made for."""
    text = text.replace("\r\n", "\n")
    if text.count(OLD) != 1:
        raise ValueError("menu.js changed, patch_menu.py needs another look")
    return text.replace(OLD, NEW)


def patch_sdkmod(source: Path, target: Path) -> None:
    """Writes a copy of the .sdkmod with the change in it."""
    with zipfile.ZipFile(source) as old, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as new:
        for entry in old.infolist():
            data = old.read(entry.filename)
            if entry.filename == MENU_JS:
                data = patch_text(data.decode("utf-8")).encode("utf-8")
            new.writestr(entry, data)


if __name__ == "__main__":
    patch_sdkmod(Path(sys.argv[1]), Path(sys.argv[2]))
