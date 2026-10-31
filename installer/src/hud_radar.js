"use strict";

// Puts markers for loot on the game's own radar. Runs in the HUD page, through the link BL4 Mod Menu
// runs. Python sends where the items and the player are, and which way the player's looking.
//
// The page can't ask that every frame, so between answers this carries on from how the player was
// moving and turning, and redraws every frame, however many of those the game runs at.
//
// The markers go in a layer of their own inside the radar, next to the game's, which fills its list
// of enemies itself and wouldn't expect anything else in there.

(function () {
    var ns = (typeof bl4linkNs !== "undefined" && bl4linkNs) || window.bl4ModMenu;
    if (!ns || !ns.ext) return;
    var ext = ns.ext;
    var KEY = "groundhider_radar";
    var POLL_BUSY_MS = 40;
    var POLL_IDLE_MS = 500;
    var LOOK_FOR_RADAR_MS = 2000;
    var MAX_PREDICT_S = 0.15;
    // How far from the middle the edge of the radar's circle is, in percent of the layer
    var REACH = 44;
    var MARKER_SIZE = 7;
    var CHUNK = 1500;
    // Worth reading once: how the game itself places things on this radar
    var SOURCES = ["coui://uiresources/enemy_radar/js/enemy_radar.js", "coui://uiresources/compass/js/compass.js"];

    if (ext.teardowns[KEY]) {
        try {
            ext.teardowns[KEY]();
        } catch (err) {}
    }

    var alive = true;
    var timer = 0;
    var frame = 0;
    var layer = null;
    var markers = [];
    var reported = null;
    var described = false;
    var language = null;

    // The last answer, how fast things were changing, and when it came
    var sample = null;

    function report(found) {
        if (reported === found) return;
        reported = found;
        ext.send(KEY, { found: found });
    }

    function sendText(label, text) {
        for (var start = 0, part = 0; start < text.length; start += CHUNK, part += 1) {
            ext.send(KEY, { label: label + "/" + part, text: text.substr(start, CHUNK) });
        }
    }

    // The game marks its pages with the language it's running in, like loc-pl
    function reportLanguage() {
        var found = document.body && /(?:^|\s)loc-([a-z-]+)/i.exec(document.body.className);
        if (found && found[1] !== language) {
            language = found[1];
            ext.send(KEY, { lang: language });
        }
    }

    function dumpModel(name) {
        var model = window[name];
        if (!model) return name + ": none";
        var parts = [];
        for (var key in model) {
            var value = model[key];
            if (typeof value === "function") continue;
            var text;
            try {
                text = JSON.stringify(value);
            } catch (err) {
                text = String(value);
            }
            parts.push(key + "=" + String(text).substr(0, 300));
        }
        return name + ": " + parts.join(" ; ");
    }

    function describe() {
        if (described) return;
        described = true;
        try {
            sendText("models", dumpModel("data_def_enemy_radar_0") + " ||| " + dumpModel("data_def_compass_0"));
            var names = [".enemy_radar_cntr", ".visual_radar", ".visual_radar_enemy_container", ".visual_radar_player", ".enemy_pip_wrapper", ".enemy_radar_pip", ".compass_cardinals_icons_wrapper"];
            var styles = [];
            for (var i = 0; i < names.length; i += 1) {
                var element = document.querySelector(names[i]);
                if (!element) continue;
                var style = window.getComputedStyle(element);
                var rect = element.getBoundingClientRect();
                styles.push(names[i] + " inline=[" + (element.getAttribute("style") || "") + "] transform=" + style.transform
                    + " perspective=" + style.perspective + " rect=" + Math.round(rect.left) + "," + Math.round(rect.top) + "," + Math.round(rect.width) + "," + Math.round(rect.height)
                    + " offset=" + element.offsetLeft + "," + element.offsetTop + "," + element.offsetWidth + "," + element.offsetHeight);
            }
            sendText("styles", styles.join(" ; "));
            SOURCES.forEach(function (url) {
                ns.get(url, function (text) {
                    if (alive && text) sendText(url.split("/").pop(), text);
                });
            });
        } catch (err) {
            sendText("describe failed", String(err));
        }
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

    function hideFrom(index) {
        for (var i = index; i < markers.length; i += 1) {
            if (markers[i].shown) {
                markers[i].shown = false;
                markers[i].element.style.display = "none";
            }
        }
    }

    function draw() {
        if (!layer || !sample || !sample.items.length) {
            hideFrom(0);
            return;
        }
        var ahead = Math.min((Date.now() - sample.at) / 1000, MAX_PREDICT_S);
        var px = sample.x + sample.vx * ahead;
        var py = sample.y + sample.vy * ahead;
        var radians = (sample.yaw + sample.turn * ahead) * Math.PI / 180;
        var cos = Math.cos(radians);
        var sin = Math.sin(radians);
        for (var i = 0; i < sample.items.length; i += 1) {
            var item = sample.items[i];
            var dx = item[0] - px;
            var dy = item[1] - py;
            var x = (-dx * sin + dy * cos) / sample.range;
            var y = -(dx * cos + dy * sin) / sample.range;
            var far = Math.sqrt(x * x + y * y);
            if (far > 1) {
                x /= far;
                y /= far;
            }
            var entry = marker(i);
            var left = (50 + x * REACH).toFixed(2) + "%";
            var top = (50 + y * REACH).toFixed(2) + "%";
            if (entry.left !== left) {
                entry.left = left;
                entry.element.style.left = left;
            }
            if (entry.top !== top) {
                entry.top = top;
                entry.element.style.top = top;
            }
            if (entry.color !== item[2]) {
                entry.color = item[2];
                entry.element.style.backgroundColor = item[2];
            }
            if (!entry.shown) {
                entry.shown = true;
                entry.element.style.display = "block";
            }
        }
        hideFrom(sample.items.length);
    }

    function everyFrame() {
        if (!alive) return;
        try {
            draw();
        } catch (err) {
            ns.log("groundhider radar: " + err);
        }
        frame = requestAnimationFrame(everyFrame);
    }

    function take(state) {
        var now = Date.now();
        if (!state || !state.m || !state.m.length) {
            sample = null;
            return;
        }
        var next = { at: now, x: state.p[0], y: state.p[1], yaw: state.y, range: state.r, items: state.m, vx: 0, vy: 0, turn: 0 };
        if (sample) {
            var gap = (now - sample.at) / 1000;
            if (gap > 0.005 && gap < 0.5) {
                next.vx = (next.x - sample.x) / gap;
                next.vy = (next.y - sample.y) / gap;
                // The short way round
                var change = ((next.yaw - sample.yaw + 540) % 360) - 180;
                next.turn = change / gap;
            }
        }
        sample = next;
    }

    function next(delay) {
        if (alive) timer = setTimeout(poll, delay);
    }

    function poll() {
        var ready = false;
        try {
            reportLanguage();
            ready = ensureLayer();
        } catch (err) {
            ns.log("groundhider radar: " + err);
        }
        if (!ready) {
            next(LOOK_FOR_RADAR_MS);
            return;
        }
        describe();
        ext.get(KEY, false, function (snap) {
            if (!alive) return;
            take(snap && snap.state);
            next(sample ? POLL_BUSY_MS : POLL_IDLE_MS);
        });
    }

    ext.teardowns[KEY] = function () {
        alive = false;
        clearTimeout(timer);
        cancelAnimationFrame(frame);
        if (layer && layer.parentNode) layer.parentNode.removeChild(layer);
        layer = null;
        markers = [];
    };

    frame = requestAnimationFrame(everyFrame);
    poll();
})();
