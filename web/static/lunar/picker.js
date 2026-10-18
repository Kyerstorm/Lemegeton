// Lunar color picker page.
//
// - The link token arrives after '#', so it's never sent to a server in a URL. It's moved
//   into this tab's sessionStorage, removed from the address bar, and sent only in the
//   Authorization header.
// - Every value that comes from users or the server (names, messages) is inserted with
//   textContent, never as HTML. Colors are only used after normalizeHex() has checked them.
// - The server re-checks everything; this page only previews and sends.
(() => {
  "use strict";

  const STORAGE_KEY = "lunarPickerToken";
  const HEX_HELP = "Enter a hex color like #FF66AA.";

  // ------------------------------------------------------------------ token

  const readToken = () => {
    const fromHash = window.location.hash.replace(/^#/, "");
    if (fromHash) {
      try { window.sessionStorage.setItem(STORAGE_KEY, fromHash); } catch (e) { /* storage blocked */ }
      window.history.replaceState(null, "", window.location.pathname);
      return fromHash;
    }
    try { return window.sessionStorage.getItem(STORAGE_KEY) || ""; } catch (e) { return ""; }
  };
  const forgetToken = () => {
    try { window.sessionStorage.removeItem(STORAGE_KEY); } catch (e) { /* storage blocked */ }
  };
  const token = readToken();

  // A newer link opened in this same tab only changes the part after '#', which doesn't
  // reload the page. Store the new token and reload so the page uses it.
  window.addEventListener("hashchange", () => {
    if (window.location.hash.length > 1) {
      readToken();
      window.location.reload();
    }
  });

  // ------------------------------------------------------------------ helpers

  const $ = (id) => document.getElementById(id);
  const all = (selector, root) => Array.from((root || document).querySelectorAll(selector));
  const show = (el, visible) => el.classList.toggle("hidden", !visible);
  const make = (tag, className, attrs) => {
    const el = document.createElement(tag);
    if (className) { el.className = className; }
    Object.entries(attrs || {}).forEach(([key, value]) => el.setAttribute(key, value));
    return el;
  };
  let uid = 0;
  const nextId = (prefix) => `${prefix}-${++uid}`;

  const duration = (seconds) => {
    seconds = Math.max(0, Math.round(seconds));
    const parts = [];
    [[86400, "d"], [3600, "h"], [60, "m"], [1, "s"]].forEach(([size, unit]) => {
      if (seconds >= size) { parts.push(Math.floor(seconds / size) + unit); seconds %= size; }
    });
    return parts.join(" ") || "0s";
  };

  // ------------------------------------------------------------------ color math

  // Same rules as the bot: #RRGGBB, RRGGBB, #RGB, RGB; pure black becomes #010101.
  const normalizeHex = (text) => {
    let value = String(text || "").trim().replace(/^#/, "");
    if (/^[0-9a-f]{3}$/i.test(value)) { value = value.replace(/./g, (c) => c + c); }
    if (!/^[0-9a-f]{6}$/i.test(value)) { return null; }
    value = value.toUpperCase();
    return "#" + (value === "000000" ? "010101" : value);
  };
  const hexToRgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const rgbToHex = (rgb) => normalizeHex(rgb.map((c) => Math.round(c).toString(16).padStart(2, "0")).join(""));
  const rgbToHsv = ([r, g, b]) => {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b);
    const d = max - Math.min(r, g, b);
    let h = 0;
    if (d) {
      if (max === r) { h = ((g - b) / d) % 6; } else if (max === g) { h = (b - r) / d + 2; } else { h = (r - g) / d + 4; }
      h = (h * 60 + 360) % 360;
    }
    return { h, s: max ? d / max : 0, v: max };
  };
  const hsvToRgb = ({ h, s, v }) => {
    const f = (n) => {
      const k = (n + h / 60) % 6;
      return (v - v * s * Math.max(0, Math.min(k, 4 - k, 1))) * 255;
    };
    return [f(5), f(3), f(1)];
  };
  const luminance = (hex) => {
    const [r, g, b] = hexToRgb(hex).map((c) => {
      c /= 255;
      return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const contrast = (a, b) => {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
  };
  const themeColor = (name) => normalizeHex(getComputedStyle(document.documentElement).getPropertyValue(name));

  // ------------------------------------------------------------------ state

  let saved = null;            // the role as the server last reported it
  const edit = { mode: "solid", primary: null, secondary: null, name: "" };
  let modesAllowed = false;    // Gradient/Holographic selectable (server has them, or the test switch)
  let busy = false;
  let writable = true;
  let expiresAt = 0;          // closes this soon without use (the server resets it on every successful call)
  let maxExpiresAt = 0;       // and this at the latest
  let nextChangeAt = null;
  let palette = [];
  const fields = [];

  const savedEdit = () => {
    const role = saved.role;
    return {
      mode: role.mode,
      primary: role.primary ? normalizeHex(role.primary) : null,
      secondary: role.secondary ? normalizeHex(role.secondary) : null,
      name: role.name || "",
    };
  };
  const colorDirty = () => {
    const s = savedEdit();
    if (edit.mode !== s.mode) { return true; }
    if (edit.mode === "solid") { return edit.primary !== s.primary; }
    if (edit.mode === "gradient") { return edit.primary !== s.primary || edit.secondary !== s.secondary; }
    return false;
  };
  const nameDirty = () => saved !== null && edit.name.trim() !== savedEdit().name;
  const isDirty = () => saved !== null && (colorDirty() || nameDirty());

  // ------------------------------------------------------------------ banners and problems

  const fatal = (title, text) => {
    $("problem-title").textContent = title;
    $("problem-text").textContent = text;
    show($("loading"), false);
    show($("app"), false);
    show($("problem"), true);
  };
  const lockPage = (title, text) => {
    writable = false;
    $("banner-access-title").textContent = title;
    $("banner-access-text").textContent = text;
    show($("banner-access"), true);
    refreshButtons();
  };
  const expired = (message) => {
    forgetToken();
    lockPage("This link expired", message || "Run /lunar color-picker in Discord for a new one. Your edits are still shown below.");
  };

  // ------------------------------------------------------------------ API

  const api = (path, options) => {
    const init = Object.assign({
      headers: { "Authorization": "Bearer " + token },
      credentials: "omit",
      cache: "no-store",
      referrerPolicy: "no-referrer",
    }, options || {});
    if (init.body !== undefined) {
      init.method = "POST";
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(init.body);
    }
    return fetch("/lunar/api/" + path, init).then((response) =>
      response.json().catch(() => ({})).then((body) => {
        if (body && body.expires_at) {
          expiresAt = body.expires_at;
          maxExpiresAt = body.max_expires_at || maxExpiresAt;
        }
        return { status: response.status, body };
      }));
  };

  // ------------------------------------------------------------------ color fields

  function makeColorField(container) {
    const key = container.dataset.colorField;          // "primary" or "secondary"
    const label = container.dataset.label;
    const ids = { label: nextId("lbl"), hex: nextId("hex"), error: nextId("err"), pop: nextId("pop") };
    let hsv = { h: 0, s: 0, v: 1 };
    let dragging = false;

    const title = make("span", "field-label", { id: ids.label });
    title.textContent = label;
    const row = make("div", "color-row");
    const button = make("button", "color-button", {
      type: "button", "aria-haspopup": "dialog", "aria-expanded": "false", "aria-controls": ids.pop,
      "aria-label": `Open the ${label.toLowerCase()} color picker`,
    });
    const hexLabel = make("label", "visually-hidden", { for: ids.hex });
    hexLabel.textContent = `${label} hex code`;
    const hex = make("input", "text-input hex-input", {
      id: ids.hex, type: "text", maxlength: "7", autocomplete: "off", spellcheck: "false",
      placeholder: "#FF66AA", "aria-describedby": ids.error,
    });
    row.append(button, hexLabel, hex);
    const error = make("p", "field-error hidden", { id: ids.error });

    const pop = make("div", "popover hidden", { id: ids.pop, role: "dialog", "aria-label": `${label} color` });
    const body = make("div", "picker-body");
    const square = make("div", "square", {
      tabindex: "0", role: "slider", "aria-label": "Saturation and brightness (arrow keys)",
      "aria-valuemin": "0", "aria-valuemax": "100",
    });
    const marker = make("div", "marker", { "aria-hidden": "true" });
    square.append(marker);
    const hue = make("input", "hue", { type: "range", min: "0", max: "359", step: "1", "aria-label": "Hue" });
    hue.style.background = "linear-gradient(to top, #F00 0%, #FF0 17%, #0F0 33%, #0FF 50%, #00F 67%, #F0F 83%, #F00 100%)";
    body.append(square, hue);
    const actions = make("div", "popover-actions");
    const done = make("button", "btn btn-secondary", { type: "button" });
    done.textContent = "Done";
    actions.append(done);
    pop.append(body, actions);
    container.append(title, row, error, pop);

    const setError = (message) => {
      error.textContent = message || "";
      show(error, Boolean(message));
      hex.setAttribute("aria-invalid", message ? "true" : "false");
    };

    const draw = () => {
      const value = edit[key];
      button.style.background = value || "";
      square.style.background =
        `linear-gradient(to top, #000, transparent), linear-gradient(to right, #FFF, transparent), hsl(${hsv.h}, 100%, 50%)`;
      marker.style.left = `${hsv.s * 100}%`;
      marker.style.top = `${(1 - hsv.v) * 100}%`;
      hue.value = String(Math.round(hsv.h));
      square.setAttribute("aria-valuenow", String(Math.round(hsv.s * 100)));
      square.setAttribute("aria-valuetext",
        `Saturation ${Math.round(hsv.s * 100)}%, brightness ${Math.round(hsv.v * 100)}%`);
    };

    // Called when the color changed somewhere else (palette, reset, the other field, typing here).
    const sync = (fromThisField) => {
      const value = edit[key];
      if (value && !fromThisField) {
        const next = rgbToHsv(hexToRgb(value));
        if (next.s === 0 || next.v === 0) { next.h = hsv.h; } // keep the hue on greys
        hsv = next;
      }
      if (document.activeElement !== hex) { hex.value = value || ""; }
      if (value) { setError(""); }
      draw();
    };

    const fromHsv = () => setColor(key, rgbToHex(hsvToRgb(hsv)), field);

    const open = (visible) => {
      show(pop, visible);
      button.setAttribute("aria-expanded", visible ? "true" : "false");
      if (visible) {
        fields.forEach((f) => { if (f !== field) { f.close(); } });
        if (!edit[key]) { fromHsv(); }
        square.focus();
      }
    };
    const close = (focusButton) => {
      if (pop.classList.contains("hidden")) { return; }
      open(false);
      if (focusButton) { button.focus(); }
    };

    const pointTo = (event) => {
      const rect = square.getBoundingClientRect();
      hsv.s = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
      hsv.v = 1 - Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height));
      fromHsv();
    };

    button.addEventListener("click", () => open(pop.classList.contains("hidden")));
    done.addEventListener("click", () => close(true));
    pop.addEventListener("keydown", (event) => {
      if (event.key === "Escape") { event.preventDefault(); close(true); }
    });
    square.addEventListener("pointerdown", (event) => {
      dragging = true;
      square.setPointerCapture(event.pointerId);
      pointTo(event);
    });
    square.addEventListener("pointermove", (event) => { if (dragging) { pointTo(event); } });
    square.addEventListener("pointerup", () => { dragging = false; });
    square.addEventListener("pointercancel", () => { dragging = false; });
    square.addEventListener("keydown", (event) => {
      const step = event.shiftKey ? 0.1 : 0.01;
      const moves = { ArrowLeft: ["s", -step], ArrowRight: ["s", step], ArrowDown: ["v", -step], ArrowUp: ["v", step] };
      const move = moves[event.key];
      if (!move) { return; }
      event.preventDefault();
      hsv[move[0]] = Math.min(1, Math.max(0, hsv[move[0]] + move[1]));
      fromHsv();
    });
    hue.addEventListener("input", () => { hsv.h = Number(hue.value); fromHsv(); });
    hex.addEventListener("input", () => {
      const value = normalizeHex(hex.value);
      if (value) { setColor(key, value, field, true); }
    });
    hex.addEventListener("blur", () => {
      const value = normalizeHex(hex.value);
      if (value) { hex.value = value; setError(""); } else if (hex.value.trim()) { setError(HEX_HELP); }
    });

    const field = {
      key, sync, close, setError, pop, button, container,
      typedValue: () => normalizeHex(hex.value),
      hasText: () => hex.value.trim() !== "",
      fromHex: (value) => {
        const next = rgbToHsv(hexToRgb(value));
        if (next.s === 0 || next.v === 0) { next.h = hsv.h; }
        hsv = next;
        draw();
      },
    };
    return field;
  }

  // setColor: the one way a color changes. source = the field that made the change (or null).
  function setColor(key, value, source, typed) {
    edit[key] = value;
    fields.forEach((f) => {
      if (f.key !== key) { return; }
      if (f === source) {
        if (typed) { f.fromHex(value); }
        f.sync(true);
      } else {
        f.sync(false);
      }
    });
    updatePalette();
    updatePreview();
  }

  // ------------------------------------------------------------------ preview

  function styleName(el) {
    el.classList.remove("gradient-text", "holo-text");
    el.style.color = "";
    el.style.backgroundImage = "";
    if (edit.mode === "holographic") {
      el.classList.add("holo-text");
    } else if (edit.mode === "gradient" && edit.primary && edit.secondary) {
      el.classList.add("gradient-text");
      el.style.backgroundImage = `linear-gradient(90deg, ${edit.primary}, ${edit.secondary})`;
    } else if (edit.primary) {
      el.style.color = edit.primary;
    }
  }

  function updatePreview() {
    if (!saved) { return; }
    all("[data-name]").forEach((el) => {
      el.textContent = saved.user.name;
      styleName(el);
    });

    const dot = $("chip-dot");
    dot.classList.remove("holo-fill");
    dot.style.background = "";
    if (edit.mode === "holographic") {
      dot.classList.add("holo-fill");
    } else if (edit.mode === "gradient" && edit.primary && edit.secondary) {
      dot.style.background = `linear-gradient(90deg, ${edit.primary}, ${edit.secondary})`;
    } else if (edit.primary) {
      dot.style.background = edit.primary;
    }
    $("chip-name").textContent = edit.name.trim() || savedEdit().name || "Unnamed";

    const bar = $("gradient-bar");
    bar.style.background = edit.primary && edit.secondary
      ? `linear-gradient(90deg, ${edit.primary}, ${edit.secondary})` : "";

    // Readability on Discord's two themes
    const colors = edit.mode === "solid" ? [edit.primary] : edit.mode === "gradient" ? [edit.primary, edit.secondary] : [];
    const dark = themeColor("--lp-preview-dark-bg");
    const light = themeColor("--lp-preview-light-bg");
    const hard = [];
    colors.filter(Boolean).forEach((c) => {
      if (dark && contrast(c, dark) < 3) { hard.push("dark"); }
      if (light && contrast(c, light) < 3) { hard.push("light"); }
    });
    const themes = Array.from(new Set(hard));
    const note = $("contrast-note");
    note.textContent = themes.length
      ? `Heads up: this color may be hard to read on Discord's ${themes.join(" and ")} theme${themes.length > 1 ? "s" : ""}.`
      : "";
    show(note, themes.length > 0);

    const dirty = isDirty();
    $("reset").disabled = !dirty;
    $("dirty-note").textContent = dirty ? "You have unsaved changes." : "No unsaved changes.";
  }

  function showIcon() {
    const icon = saved.role.icon;
    all("[data-icon-img]").forEach((img) => {
      const isImage = Boolean(icon && icon.type === "image");
      if (isImage) { img.src = icon.url; }
      show(img, isImage);
    });
    all("[data-icon-emoji]").forEach((el) => {
      const isEmoji = Boolean(icon && icon.type === "emoji");
      el.textContent = isEmoji ? icon.value : "";
      show(el, isEmoji);
    });
    const current = $("icon-current");
    current.textContent = "";
    if (icon && icon.type === "image") {
      const img = make("img", "role-icon", { alt: "Your current role icon", referrerpolicy: "no-referrer" });
      img.src = icon.url;
      current.append(img);
    } else if (icon && icon.type === "emoji") {
      current.textContent = icon.value;
    } else {
      current.textContent = "None";
    }
  }

  // ------------------------------------------------------------------ style switch and palette

  function showMode() {
    all('input[name="mode"]').forEach((input) => { input.checked = input.value === edit.mode; });
    ["solid", "gradient", "holographic"].forEach((mode) => show($(`panel-${mode}`), edit.mode === mode));
    show($("palette"), edit.mode !== "holographic");
    $("palette-primary-legend").textContent = edit.mode === "gradient" ? "Primary" : "Color";
    show($("palette-secondary"), edit.mode === "gradient" && palette.length > 0);
    fields.forEach((f) => f.close(false));
  }

  function buildPalette() {
    ["primary", "secondary"].forEach((key) => {
      const group = $(`palette-${key}`);
      const grid = group.querySelector(".swatches");
      grid.textContent = "";
      palette.forEach((color) => {
        const id = nextId("sw");
        const input = make("input", "", { type: "radio", name: `palette-${key}`, id, value: color });
        const label = make("label", "", { for: id, title: color });
        label.style.background = color;
        const text = make("span", "visually-hidden");
        text.textContent = color;
        label.append(text);
        input.addEventListener("change", () => { if (input.checked) { setColor(key, color, null); } });
        grid.append(input, label);
      });
      show(group, palette.length > 0 && (key === "primary" || edit.mode === "gradient"));
    });
    updatePalette();
  }

  function updatePalette() {
    ["primary", "secondary"].forEach((key) => {
      all(`input[name="palette-${key}"]`).forEach((input) => { input.checked = input.value === edit[key]; });
    });
  }

  // ------------------------------------------------------------------ buttons and saving

  function cooling() {
    return nextChangeAt !== null && nextChangeAt * 1000 > Date.now();
  }

  function refreshButtons() {
    all("[data-set]").forEach((button) => {
      button.disabled = busy || !writable || cooling();
    });
  }

  function setStatus(id, ok, message, notes) {
    const el = $(id);
    el.textContent = "";
    el.className = "status " + (ok ? "status-ok" : "status-error");
    el.textContent = message || "";
    (notes || []).forEach((note) => {
      const line = make("span", "status-note");
      line.textContent = note;
      el.append(line);
    });
  }

  function applySaved(state, part) {
    saved = state;
    nextChangeAt = state.next_change_at;
    const fresh = savedEdit();
    if (part === "color") {
      edit.mode = fresh.mode;
      edit.primary = fresh.primary;
      edit.secondary = fresh.secondary || edit.secondary;
    } else if (part === "name") {
      edit.name = fresh.name;
      $("name-input").value = fresh.name;
      updateNameCount();
    }
    fields.forEach((f) => f.sync(false));
    showMode();
    showIcon();
    updatePalette();
    updatePreview();
    tickCooldown();
  }

  function save(kind, button) {
    if (busy || !writable) { return; }
    let path = "color";
    let body;
    const statusId = `status-${kind}`;
    if (kind === "name") {
      path = "name";
      body = { name: $("name-input").value };
    } else if (kind === "holographic") {
      body = { mode: "holographic" };
    } else {
      const needed = kind === "gradient" ? ["primary", "secondary"] : ["primary"];
      const missing = needed.filter((key) => !edit[key]);
      if (missing.length) {
        fields.filter((f) => missing.includes(f.key) && !f.container.closest(".hidden")).forEach((f) => f.setError(HEX_HELP));
        setStatus(statusId, false, kind === "gradient" ? "Pick both colors first." : "Pick a color first.");
        return;
      }
      body = { mode: kind, primary: edit.primary };
      if (kind === "gradient") { body.secondary = edit.secondary; }
    }

    busy = true;
    const label = button.textContent;
    button.textContent = "Saving…";
    button.setAttribute("aria-busy", "true");
    refreshButtons();
    setStatus(statusId, true, "");

    api(path, { body }).then(({ status, body: reply }) => {
      const message = (reply && reply.message) || "Something went wrong. Try again in a moment.";
      if (status === 401) { expired(message); setStatus(statusId, false, message); return; }
      if (status === 403) { lockPage("You can't change this role right now", message); setStatus(statusId, false, message); return; }
      if (status !== 200) { setStatus(statusId, false, message); return; }
      if (reply.retry_at) { nextChangeAt = reply.retry_at; tickCooldown(); }
      setStatus(statusId, reply.ok, message, reply.notes);
      if (kind === "name") {
        const err = $("name-error");
        err.textContent = reply.ok ? "" : message;
        show(err, !reply.ok);
        $("name-input").setAttribute("aria-invalid", reply.ok ? "false" : "true");
      }
      if (reply.ok && reply.state) { applySaved(reply.state, kind === "name" ? "name" : "color"); }
    }).catch(() => {
      setStatus(statusId, false, "Can't reach the bot. Check your connection and try again.");
    }).finally(() => {
      busy = false;
      button.textContent = label;
      button.removeAttribute("aria-busy");
      refreshButtons();
    });
  }

  // ------------------------------------------------------------------ timers

  let cooldownTimer = null;
  function tickCooldown() {
    window.clearTimeout(cooldownTimer);
    const note = $("cooldown-note");
    if (cooling()) {
      note.textContent = `You can change your role again in ${duration(nextChangeAt - Date.now() / 1000)}.`;
      show(note, true);
      cooldownTimer = window.setTimeout(tickCooldown, 1000);
    } else {
      nextChangeAt = null;
      show(note, false);
    }
    refreshButtons();
  }

  function tickExpiry() {
    const now = Date.now() / 1000;
    const left = Math.min(expiresAt, maxExpiresAt || expiresAt) - now;
    if (left <= 0) {
      $("expires").textContent = "now";
      $("expires-max").textContent = "now";
      expired();
      return;
    }
    $("expires").textContent = `in ${duration(left)}`;
    $("expires-max").textContent = `in ${duration(maxExpiresAt - now)}`;
    window.setTimeout(tickExpiry, 1000);
  }

  // ------------------------------------------------------------------ tabs, name, reset

  function setupTabs() {
    const tabs = all('[role="tab"]');
    const select = (tab, focus) => {
      tabs.forEach((t) => {
        const on = t === tab;
        t.setAttribute("aria-selected", on ? "true" : "false");
        t.tabIndex = on ? 0 : -1;
        show($(t.getAttribute("aria-controls")), on);
      });
      fields.forEach((f) => f.close(false));
      if (focus) { tab.focus(); }
    };
    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => select(tab, false));
      tab.addEventListener("keydown", (event) => {
        const moves = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: tabs.length - 1 };
        if (!(event.key in moves)) { return; }
        event.preventDefault();
        select(tabs[(moves[event.key] + tabs.length) % tabs.length], true);
      });
    });
  }

  function updateNameCount() {
    const input = $("name-input");
    $("name-count").textContent = `${input.value.length}/${input.maxLength} characters`;
  }

  function reset() {
    Object.assign(edit, savedEdit());
    $("name-input").value = edit.name;
    $("name-input").setAttribute("aria-invalid", "false");
    show($("name-error"), false);
    updateNameCount();
    fields.forEach((f) => { f.setError(""); f.sync(false); });
    showMode();
    updatePalette();
    updatePreview();
  }

  // ------------------------------------------------------------------ start

  function render(data) {
    saved = data.state;
    nextChangeAt = saved.next_change_at;
    Object.assign(edit, savedEdit());

    const guild = saved.guild;
    modesAllowed = Boolean(guild.gradient || guild.preview_enhanced);
    show($("banner-debug"), Boolean(guild.preview_enhanced));
    show($("mode-hint"), !guild.gradient);
    ["gradient", "holographic"].forEach((mode) => { $(`mode-${mode}`).disabled = !modesAllowed; });

    all("[data-avatar]").forEach((img) => { img.src = saved.user.avatar_url; });
    const time = new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    all("[data-time]").forEach((el) => { el.textContent = `Today at ${time}`; });

    all("[data-color-field]").forEach((container) => fields.push(makeColorField(container)));
    fields.forEach((f) => f.sync(false));

    const nameInput = $("name-input");
    nameInput.maxLength = saved.name_max || 100;
    nameInput.value = edit.name;
    updateNameCount();
    nameInput.addEventListener("input", () => {
      edit.name = nameInput.value;
      updateNameCount();
      show($("name-error"), false);
      nameInput.setAttribute("aria-invalid", "false");
      updatePreview();
    });

    all('input[name="mode"]').forEach((input) => input.addEventListener("change", () => {
      if (input.checked) { edit.mode = input.value; showMode(); updatePalette(); updatePreview(); }
    }));
    all("[data-set]").forEach((button) => button.addEventListener("click", () => save(button.dataset.set, button)));
    $("reset").addEventListener("click", reset);
    document.addEventListener("pointerdown", (event) => {
      fields.forEach((f) => {
        if (!f.pop.contains(event.target) && !f.button.contains(event.target)) { f.close(false); }
      });
    });
    window.addEventListener("beforeunload", (event) => {
      if (isDirty()) { event.preventDefault(); event.returnValue = ""; }
    });

    setupTabs();
    showMode();
    showIcon();
    updatePreview();
    show($("loading"), false);
    show($("app"), true);
    tickExpiry();
    tickCooldown();

    api("palette").then(({ status, body }) => {
      const statusEl = $("palette-status");
      if (status === 200 && body.ok && body.colors.length) {
        palette = body.colors.map(normalizeHex).filter(Boolean);
        statusEl.textContent = "Pick one to fill in the color, then press Set.";
      } else {
        statusEl.textContent = (body && body.message) || "Couldn't read colors from your avatar.";
      }
      buildPalette();
      showMode();
    }).catch(() => { $("palette-status").textContent = "Couldn't load colors from your avatar."; });
  }

  function start() {
    if (!token) {
      fatal("No link found", "Open this page from the button that /lunar color-picker gives you in Discord.");
      return;
    }
    api("state").then(({ status, body }) => {
      if (status === 200 && body.ok) { render(body); return; }
      const message = (body && body.message) || "Something went wrong. Try again in a moment.";
      if (status === 401) { forgetToken(); fatal("This link expired", message); return; }
      fatal("Can't open the picker", message);
    }).catch(() => fatal("Can't reach the bot", "Check your connection and reload the page."));
  }

  document.addEventListener("DOMContentLoaded", start);
})();
