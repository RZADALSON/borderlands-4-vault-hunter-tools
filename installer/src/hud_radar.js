"use strict";

// Puts markers for loot on the game's own radar. Runs in the HUD page, through the link BL4 Mod Menu
// runs. Python sends where they go, as -1 to 1 either way from the middle, up being where you look.
//
// The markers go in a layer of their own inside the radar, next to the game's, which fills its list
// of enemies itself and wouldn't expect anything else in there.

(function () {
    var ns = (typeof bl4linkNs !== "undefined" && bl4linkNs) || window.bl4ModMenu;
    if (!ns || !ns.ext) return;
    var ext = ns.ext;
    var KEY = "groundhider_radar";
    var POLL_BUSY_MS = 100;
    var POLL_IDLE_MS = 500;
    var LOOK_FOR_RADAR_MS = 2000;
    // How far from the middle the edge of the radar's circle is, in percent of the layer
    var REACH = 44;
    var MARKER_SIZE = 7;

    if (ext.teardowns[KEY]) {
        try {
            ext.teardowns[KEY]();
        } catch (err) {}
    }

    var alive = true;
    var timer = 0;
    var layer = null;
    var markers = [];
    var reported = null;

    function report(found) {
        if (reported === found) return;
        reported = found;
        ext.send(KEY, { found: found });
    }

    function ensureLayer() {
        if (layer && layer.parentNode && document.body.contains(layer)) return true;
        var radar = document.querySelector(".visual_radar");
        report(!!radar);
        if (!radar) return false;
        layer = document.createElement("div");
        layer.className = "groundhider_radar_layer";
        layer.style.position = "absolute";
        layer.style.left = "0";
        layer.style.top = "0";
        layer.style.width = "100%";
        layer.style.height = "100%";
        // Above the radar's art, under nothing that takes the mouse: this page doesn't have any
        layer.style.zIndex = "5";
        layer.style.pointerEvents = "none";
        radar.appendChild(layer);
        markers = [];
        return true;
    }

    function marker(index) {
        while (markers.length <= index) {
            var dot = document.createElement("div");
            dot.style.position = "absolute";
            dot.style.width = MARKER_SIZE + "%";
            dot.style.height = MARKER_SIZE + "%";
            dot.style.marginLeft = (-MARKER_SIZE / 2) + "%";
            dot.style.marginTop = (-MARKER_SIZE / 2) + "%";
            dot.style.borderRadius = "50%";
            dot.style.borderStyle = "solid";
            dot.style.borderWidth = "3px";
            dot.style.borderColor = "#000000";
            dot.style.display = "none";
            layer.appendChild(dot);
            markers.push({ element: dot, shown: false, left: "", top: "", color: "" });
        }
        return markers[index];
    }

    function show(items) {
        for (var i = 0; i < items.length; i += 1) {
            var entry = marker(i);
            var left = (50 + items[i][0] * REACH).toFixed(1) + "%";
            var top = (50 + items[i][1] * REACH).toFixed(1) + "%";
            if (entry.left !== left) {
                entry.left = left;
                entry.element.style.left = left;
            }
            if (entry.top !== top) {
                entry.top = top;
                entry.element.style.top = top;
            }
            if (entry.color !== items[i][2]) {
                entry.color = items[i][2];
                entry.element.style.backgroundColor = items[i][2];
            }
            if (!entry.shown) {
                entry.shown = true;
                entry.element.style.display = "block";
            }
        }
        for (var j = items.length; j < markers.length; j += 1) {
            if (markers[j].shown) {
                markers[j].shown = false;
                markers[j].element.style.display = "none";
            }
        }
    }

    function next(delay) {
        if (alive) timer = setTimeout(poll, delay);
    }

    function poll() {
        var ready = false;
        try {
            ready = ensureLayer();
        } catch (err) {
            ns.log("groundhider radar: " + err);
        }
        if (!ready) {
            next(LOOK_FOR_RADAR_MS);
            return;
        }
        ext.get(KEY, false, function (snap) {
            if (!alive) return;
            var items = snap && snap.state && snap.state.m ? snap.state.m : [];
            try {
                ensureLayer();
                show(items);
            } catch (err) {
                ns.log("groundhider radar: " + err);
            }
            next(items.length ? POLL_BUSY_MS : POLL_IDLE_MS);
        });
    }

    ext.teardowns[KEY] = function () {
        alive = false;
        clearTimeout(timer);
        if (layer && layer.parentNode) layer.parentNode.removeChild(layer);
        layer = null;
        markers = [];
    };

    poll();
})();
