// Custom role color picker page.
import { clamp, contrast, duration, formatSize, hexToRgb, hsvToRgb, normalizeHex, rgbToHex, rgbToHsv, type HSV } from "./picker-utils";
//
// - The link token arrives after '#', so it's never sent to a server in a URL. It's moved
//   into this tab's sessionStorage, removed from the address bar, and sent only in the
//   Authorization header.
// - Every value that comes from users or the server (names, messages) is inserted with
//   textContent, never as HTML. Colors are only used after normalizeHex() has checked them.
// - Images are only ever data: or blob: URLs (the page's CSP allows nothing remote).
// - The server re-checks everything; this page only previews and sends.
// Preserves the original picker interactions while mounting inside the static Next route.
// The token remains in the URL fragment/session storage and is sent only in Authorization.

type PickerMode = "solid" | "gradient" | "holographic";
type ColorKey = "primary" | "secondary";
type SaveKind = PickerMode | "name";
type PickerPart = "color" | "name" | "icon";

interface Crop {
  x: number;
  y: number;
  size: number;
}

type RoleIcon =
  | { type: "image"; url: string; crop?: Crop | null; has_source?: boolean }
  | { type: "emoji"; value: string }
  | null;

interface PickerState {
  role: {
    mode: PickerMode;
    primary: string | null;
    secondary: string | null;
    name: string;
    icon: RoleIcon;
  };
  user: { name: string; avatar_url?: string | null };
  guild: {
    gradient?: boolean;
    preview_enhanced?: boolean;
    icons?: boolean;
    preview_icons?: boolean;
  };
  icon_source_max: number;
  name_max?: number;
  next_change_at: number | null;
}

interface PickerReply {
  ok?: boolean;
  message?: string;
  error?: string;
  state?: PickerState;
  notes?: string[];
  retry_at?: number;
  colors?: string[];
  expires_at?: number | string;
  max_expires_at?: number | string;
}

interface PickerRequestOptions {
  body?: Record<string, unknown>;
  form?: FormData;
  method?: string;
}

interface ColorField {
  key: ColorKey;
  sync(fromThisField: boolean): void;
  close(focusButton?: boolean): void;
  setError(message: string): void;
  pop: HTMLElement;
  button: HTMLButtonElement;
  container: HTMLElement;
  fromHex(value: string): void;
}

interface PickerEdit {
  mode: PickerMode;
  primary: string | null;
  secondary: string | null;
  name: string;
}

interface IconEdit {
  blob: Blob | null;
  url: string | null;
  img: HTMLImageElement | null;
  w: number;
  h: number;
  crop: Crop | null;
  emoji: string;
}
export function mountCustomRolePicker(root: HTMLElement): () => void {

  const STORAGE_KEY = "customRolePickerToken";
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
  const cleanups: Array<() => void> = [];

  // A newer link opened in this same tab only changes the part after '#', which doesn't
  // reload the page. Store the new token and reload so the page uses it.
  const handleHashChange = () => {
    if (window.location.hash.length > 1) {
      readToken();
      window.location.reload();
    }
  };
  window.addEventListener("hashchange", handleHashChange);
  cleanups.push(() => window.removeEventListener("hashchange", handleHashChange));

  // ------------------------------------------------------------------ helpers

  const $ = <T extends HTMLElement = HTMLElement>(id: string): T => root.querySelector<T>("#" + id)!;
  const all = <T extends Element = HTMLElement>(selector: string, scope: ParentNode = root): T[] => Array.from(scope.querySelectorAll<T>(selector));
  const show = (el: Element, visible: boolean): void => {
    el.classList.toggle("hidden", !visible);
  };
  const make = <K extends keyof HTMLElementTagNameMap>(tag: K, className = "", attrs: Record<string, string> = {}): HTMLElementTagNameMap[K] => {
    const el = document.createElement(tag);
    if (className) { el.className = className; }
    Object.entries(attrs || {}).forEach(([key, value]) => el.setAttribute(key, value));
    return el;
  };
  let uid = 0;
  const nextId = (prefix: string): string => `${prefix}-${++uid}`;

  // Color conversion and contrast helpers live in picker-utils.ts.

  const themeColor = (name: string): string | null => normalizeHex(getComputedStyle(document.documentElement).getPropertyValue(name));

  // ------------------------------------------------------------------ state

  let saved: PickerState | null = null;            // the role as the server last reported it
  const edit: PickerEdit = { mode: "solid", primary: null, secondary: null, name: "" };
  let modesAllowed = false;    // Gradient/Holographic selectable (server has them, or the test switch)
  let iconsUsable = false;     // Role Icon tab usable (server has Role Icons, or the test switch)
  let busy = false;
  let writable = true;
  let expiresAt = 0;           // closes this soon without use (the server resets it on every successful call)
  let maxExpiresAt = 0;        // and this at the latest
  let nextChangeAt: number | null = null;
  let palette: string[] = [];
  const fields: ColorField[] = [];

  // A role icon being prepared: an image (the original file, never re-encoded here) with its crop
  // square in the image's own pixels, and/or an emoji. Which one is pending depends on the
  // "Icon from" switch.
  const iconEdit: IconEdit = { blob: null, url: null, img: null, w: 0, h: 0, crop: null, emoji: "" };
  let previewUrl: string | null = null;       // data: URL of the current crop, for the preview cards

  const savedEdit = () => {
    const role = saved!.role;
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
  const iconSource = (): "upload" | "link" | "emoji" => {
    const checked = root.querySelector<HTMLInputElement>('input[name="icon-source"]:checked');
    const value = checked?.value;
    return value === "link" || value === "emoji" ? value : "upload";
  };
  const iconPending = (): "emoji" | "image" | null => {
    if (iconSource() === "emoji") { return iconEdit.emoji ? "emoji" : null; }
    return iconEdit.url ? "image" : null;
  };
  const isDirty = () => saved !== null && (colorDirty() || nameDirty() || iconPending() !== null);

  // ------------------------------------------------------------------ banners and problems

  const fatal = (title: string, text: string): void => {
    $("problem-title").textContent = title;
    $("problem-text").textContent = text;
    show($("loading"), false);
    show($("app"), false);
    show($("problem"), true);
  };
  const lockPage = (title: string, text: string): void => {
    writable = false;
    $("banner-access-title").textContent = title;
    $("banner-access-text").textContent = text;
    show($("banner-access"), true);
    refreshButtons();
  };
  const expired = (message?: string): void => {
    forgetToken();
    lockPage("This link expired", message || "Run /custom-role in Discord and press Color picker for a new one. Your edits are still shown below.");
  };

  // ------------------------------------------------------------------ API

  const noteExpiry = (expires: string | number | null, latest: string | number | null): void => {
    if (expires) {
      expiresAt = Number(expires);
      maxExpiresAt = Number(latest) || maxExpiresAt;
    }
  };

  // options: {body} = JSON POST, {form} = multipart POST, {method} = e.g. DELETE
  const request = (path: string, options: PickerRequestOptions = {}): Promise<Response> => {
    const opts = options || {};
    const headers = new Headers({ Authorization: "Bearer " + token });
    const init: RequestInit = {
      headers,
      credentials: "omit",
      cache: "no-store",
      referrerPolicy: "no-referrer",
    };
    if (opts.method) { init.method = opts.method; }
    if (opts.body !== undefined) {
      init.method = "POST";
      headers.set("Content-Type", "application/json");
      init.body = JSON.stringify(opts.body);
    }
    if (opts.form) {
      init.method = "POST";
      init.body = opts.form;
    }
    return fetch("/custom-roles/api/" + path, init).then((response) => {
      noteExpiry(response.headers.get("X-Picker-Expires-At"), response.headers.get("X-Picker-Max-Expires-At"));
      return response;
    });
  };
  const readJson = async (response: Response): Promise<{ status: number; body: PickerReply }> => {
    const body = await response.json().catch(() => ({})) as PickerReply;
    noteExpiry(body.expires_at ?? null, body.max_expires_at ?? null);
    return { status: response.status, body };
  };
  const api = (path: string, options: PickerRequestOptions = {}): Promise<{ status: number; body: PickerReply }> => request(path, options).then(readJson);

  // ------------------------------------------------------------------ color fields

  function makeColorField(container: HTMLElement): ColorField {
    const key = container.dataset.colorField as ColorKey; // "primary" or "secondary"
    const label = container.dataset.label || "Color";
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

    const setError = (message: string): void => {
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
    const sync = (fromThisField: boolean): void => {
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

    const open = (visible: boolean): void => {
      show(pop, visible);
      button.setAttribute("aria-expanded", visible ? "true" : "false");
      if (visible) {
        fields.forEach((f) => { if (f !== field) { f.close(); } });
        if (!edit[key]) { fromHsv(); }
        square.focus();
      }
    };
    const close = (focusButton = false): void => {
      if (pop.classList.contains("hidden")) { return; }
      open(false);
      if (focusButton) { button.focus(); }
    };

    const pointTo = (event: PointerEvent): void => {
      const rect = square.getBoundingClientRect();
      hsv.s = clamp((event.clientX - rect.left) / rect.width, 0, 1);
      hsv.v = 1 - clamp((event.clientY - rect.top) / rect.height, 0, 1);
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
      const moves: Record<string, ["s" | "v", number]> = { ArrowLeft: ["s", -step], ArrowRight: ["s", step], ArrowDown: ["v", -step], ArrowUp: ["v", step] };
      const move = moves[event.key];
      if (!move) { return; }
      event.preventDefault();
      hsv[move[0]] = clamp(hsv[move[0]] + move[1], 0, 1);
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

    const field: ColorField = {
      key, sync, close, setError, pop, button, container,
      fromHex: (value: string): void => {
        const next = rgbToHsv(hexToRgb(value));
        if (next.s === 0 || next.v === 0) { next.h = hsv.h; }
        hsv = next;
        draw();
      },
    };
    return field;
  }

  // setColor: the one way a color changes. source = the field that made the change (or null).
  function setColor(key: ColorKey, value: string | null, source: ColorField | null, typed = false): void {
    edit[key] = value;
    fields.forEach((f) => {
      if (f.key !== key) { return; }
      if (f === source) {
        if (typed && value) { f.fromHex(value); }
        f.sync(true);
      } else {
        f.sync(false);
      }
    });
    updatePalette();
    updatePreview();
  }

  // ------------------------------------------------------------------ preview

  function styleName(el: HTMLElement): void {
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

  // The icon shown next to the name: what's being prepared, or else the saved one.
  function renderPreviewIcon() {
    let icon: RoleIcon = saved!.role.icon;
    const pending = iconPending();
    if (pending === "image" && previewUrl) {
      icon = { type: "image", url: previewUrl };
    } else if (pending === "emoji") {
      icon = { type: "emoji", value: iconEdit.emoji };
    }
    all<HTMLImageElement>("[data-icon-img]").forEach((img) => {
      const isImage = icon?.type === "image";
      if (isImage) img.src = icon.url;
      show(img, isImage);
    });
    all("[data-icon-emoji]").forEach((el) => {
      const isEmoji = icon?.type === "emoji";
      el.textContent = isEmoji ? icon.value : "";
      show(el, isEmoji);
    });
  }

  function updatePreview() {
    const current = saved;
    if (!current) { return; }
    const username = current.user.name;
    all("[data-name]").forEach((el) => {
      el.textContent = username;
      styleName(el);
    });
    renderPreviewIcon();

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
    const colors: Array<string | null> = edit.mode === "solid" ? [edit.primary] : edit.mode === "gradient" ? [edit.primary, edit.secondary] : [];
    const dark = themeColor("--cr-preview-dark-bg");
    const light = themeColor("--cr-preview-light-bg");
    const hard: string[] = [];
    colors.filter((color): color is string => Boolean(color)).forEach((c) => {
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
    $<HTMLButtonElement>("reset").disabled = !dirty;
    $("dirty-note").textContent = dirty ? "You have unsaved changes." : "No unsaved changes.";
    refreshButtons();
  }

  function showIcon() {
    const icon = saved!.role.icon;
    const current = $("icon-current");
    current.textContent = "";
    if (icon && icon.type === "image") {
      const img = make("img", "role-icon", { alt: "Your current role icon" });
      img.src = icon.url;
      current.append(img);
    } else if (icon && icon.type === "emoji") {
      current.textContent = icon.value;
    } else {
      current.textContent = "None";
    }
    renderPreviewIcon();
  }

  // ------------------------------------------------------------------ style switch and palette

  function showMode() {
    all<HTMLInputElement>('input[name="mode"]').forEach((input) => { input.checked = input.value === edit.mode; });
    (["solid", "gradient", "holographic"] as const).forEach((mode) => show($(`panel-${mode}`), edit.mode === mode));
    show($("palette"), edit.mode !== "holographic");
    $("palette-primary-legend").textContent = edit.mode === "gradient" ? "Primary" : "Color";
    show($("palette-secondary"), edit.mode === "gradient" && palette.length > 0);
    fields.forEach((f) => f.close(false));
  }

  function buildPalette() {
    (["primary", "secondary"] as const).forEach((key: ColorKey) => {
      const group = $(`palette-${key}`);
      const grid = group.querySelector<HTMLElement>(".swatches");
      if (!grid) return;
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
    (["primary", "secondary"] as const).forEach((key: ColorKey) => {
      all<HTMLInputElement>(`input[name="palette-${key}"]`).forEach((input) => { input.checked = input.value === edit[key]; });
    });
  }

  // ------------------------------------------------------------------ role icon: loading and cropping

  const PNG_SIGNATURE = [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A];
  const MAX_SIDE = 8192;          // same limits and messages as the server (images.py)
  const MAX_PIXELS = 16000000;
  const PHOTO_HINT = "Try a 12 MP photo or a screenshot.";
  const HEIC_MESSAGE = "iPhone HEIC photos aren't supported. Save it as JPEG or PNG (or take a screenshot) and try again.";
  const HEIF_BRANDS = ["heic", "heix", "hevc", "hevx", "heim", "heis", "hevm", "hevs", "mif1", "msf1"];
  const MIN_CROP = 16;
  const PREVIEW_SIDE = 128;       // canvas size for the live preview (shown smaller)
  let previewFrame = 0;

  // Width and height from the file's header, read BEFORE the browser decodes anything, so a
  // decompression bomb (a small file with huge dimensions) is refused without being opened.
  // JPEG sizes are as displayed (a phone photo's EXIF rotation applied), like the server's.
  // Returns null if no size header was found in the bytes given.
  function headerSize(bytes: Uint8Array, isPng: boolean): { w: number; h: number } | null {
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    if (isPng) {
      return bytes.length >= 24 ? { w: view.getUint32(16), h: view.getUint32(20) } : null;
    }
    let turned = false;
    let i = 2;  // JPEG: walk the markers to the first "start of frame"
    while (i + 9 < bytes.length) {
      if (bytes[i] !== 0xFF) { i += 1; continue; }
      const marker = bytes[i + 1];
      if (marker === 0xFF) { i += 1; continue; }
      if (marker === 0xD8 || marker === 0x01 || (marker >= 0xD0 && marker <= 0xD7)) { i += 2; continue; }
      const length = view.getUint16(i + 2);
      if (marker === 0xE1) {
        turned = turned || [5, 6, 7, 8].includes(exifOrientation(bytes, view, i + 4, Math.min(i + 2 + length, bytes.length)));
      }
      if (marker >= 0xC0 && marker <= 0xCF && marker !== 0xC4 && marker !== 0xC8 && marker !== 0xCC) {
        const h = view.getUint16(i + 5);
        const w = view.getUint16(i + 7);
        return turned ? { w: h, h: w } : { w, h };
      }
      i += 2 + length;
    }
    return null;
  }

  // The EXIF orientation tag from an APP1 segment (bytes start..end), or 0 if there isn't one.
  function exifOrientation(bytes: Uint8Array, view: DataView, start: number, end: number): number {
    const exif = [0x45, 0x78, 0x69, 0x66, 0, 0];  // "Exif\0\0"
    if (end - start < 16 || !exif.every((byte, k) => bytes[start + k] === byte)) { return 0; }
    const tiff = start + 6;
    const little = bytes[tiff] === 0x49;  // "II" = little-endian, "MM" = big-endian
    const ifd = tiff + view.getUint32(tiff + 4, little);
    if (ifd + 2 > end) { return 0; }
    const count = view.getUint16(ifd, little);
    for (let k = 0; k < count && ifd + 2 + (k + 1) * 12 <= end; k += 1) {
      const entry = ifd + 2 + k * 12;
      if (view.getUint16(entry, little) === 0x0112) { return view.getUint16(entry + 8, little); }
    }
    return 0;
  }

  // HEIC/HEIF (iPhone photos) by their "ftyp" box; AVIF uses the same container and isn't counted.
  function isHeif(bytes: Uint8Array): boolean {
    const text = (from: number, to: number): string => String.fromCharCode(...bytes.subarray(from, to));
    if (bytes.length < 12 || text(4, 8) !== "ftyp") { return false; }
    const boxEnd = Math.min(Math.max(new DataView(bytes.buffer, bytes.byteOffset).getUint32(0), 16), 256, bytes.length);
    const brands = [text(8, 12)];
    for (let k = 16; k + 4 <= boxEnd; k += 4) { brands.push(text(k, k + 4)); }
    return !brands.some((b) => b === "avif" || b === "avis") && brands.some((b) => HEIF_BRANDS.includes(b));
  }

  // The refusal for an image too large in pixels, naming the limit hit (same wording as the server).
  function pixelLimitError(w: number, h: number): string | null {
    const overTotal = w * h > MAX_PIXELS;
    let message;
    if (w > MAX_SIDE && h > MAX_SIDE) {
      message = `This image is ${w}x${h} px; the limit is ${MAX_SIDE} px per side.`;
    } else if (h > MAX_SIDE) {
      message = `This image is ${h} px tall; the limit is ${MAX_SIDE} px per side.`;
    } else if (w > MAX_SIDE) {
      message = `This image is ${w} px wide; the limit is ${MAX_SIDE} px per side.`;
    } else if (overTotal) {
      const millions = Math.ceil(w * h / 100000) / 10;  // rounded up, so it never reads as "16.0"
      message = `This image is ${w}x${h} px (${millions} million pixels); the limit is ${MAX_PIXELS / 1000000} million pixels.`;
    } else {
      return null;
    }
    return overTotal ? `${message} ${PHOTO_HINT}` : message;
  }

  const validCrop = (crop: Crop | null | undefined, w: number, h: number): crop is Crop =>
    crop !== null && crop !== undefined
    && [crop.x, crop.y, crop.size].every(Number.isInteger)
    && crop.size >= MIN_CROP && crop.x >= 0 && crop.y >= 0 && crop.x + crop.size <= w && crop.y + crop.size <= h;

  function clearIconImage() {
    if (iconEdit.url) { URL.revokeObjectURL(iconEdit.url); }
    Object.assign(iconEdit, { blob: null, url: null, img: null, w: 0, h: 0, crop: null });
    previewUrl = null;
    show($("crop"), false);
    $<HTMLImageElement>("crop-img").removeAttribute("src");
    $<HTMLImageElement>("crop-preview").removeAttribute("src");
  }

  // Check a chosen or downloaded image like the server will, then open it in the crop editor.
  async function loadImageBlob(blob: Blob, crop: Crop | null = null): Promise<void> {
    const max = saved!.icon_source_max;
    if (blob.size > max) {
      throw new Error(`That image is ${formatSize(blob.size)}. Images can be at most ${formatSize(max)}.`);
    }
    const head = new Uint8Array(await blob.slice(0, 256 * 1024).arrayBuffer());
    const isPng = PNG_SIGNATURE.every((byte, i) => head[i] === byte);
    const isJpeg = head[0] === 0xFF && head[1] === 0xD8 && head[2] === 0xFF;
    if (!isPng && !isJpeg) {
      throw new Error(isHeif(head) ? HEIC_MESSAGE
        : "Only PNG or JPEG images work as role icons (checked by the file's content, not its name).");
    }
    const declared = headerSize(head, isPng);
    if (!declared) {
      throw new Error("I couldn't read that image. It may be damaged.");
    }
    const tooBig = pixelLimitError(declared.w, declared.h);
    if (tooBig) {
      throw new Error(tooBig);
    }
    const url = URL.createObjectURL(blob);
    const probe = new Image();
    try {
      // load/error events, not decode(): decode() can wait forever in a hidden or background tab.
      await new Promise<void>((resolve, reject) => {
        probe.addEventListener("load", () => resolve(), { once: true });
        probe.addEventListener("error", () => reject(new Error("Image load failed.")), { once: true });
        probe.src = url;
      });
    } catch (e) {
      URL.revokeObjectURL(url);
      throw new Error("I couldn't read that image. It may be damaged.");
    }
    const w = probe.naturalWidth;
    const h = probe.naturalHeight;
    const decodedTooBig = pixelLimitError(w, h);
    if (decodedTooBig) {
      URL.revokeObjectURL(url);
      throw new Error(decodedTooBig);
    }
    clearIconImage();
    const side = Math.min(w, h);
    Object.assign(iconEdit, {
      blob, url, w, h, img: probe,  // already decoded: the preview draws from it
      crop: validCrop(crop, w, h)
        ? { x: crop.x, y: crop.y, size: crop.size }
        : { x: Math.floor((w - side) / 2), y: Math.floor((h - side) / 2), size: side },
    });
    $<HTMLImageElement>("crop-img").src = url;
    $<HTMLInputElement>("crop-zoom").max = String(Math.max(1, Math.min(10, side / MIN_CROP)));
    show($("crop"), true);
    layoutCrop();
    updatePreview();
  }

  function clampCrop(): void {
    const c = iconEdit.crop;
    if (!c) return;
    const side = Math.min(iconEdit.w, iconEdit.h);
    c.size = clamp(c.size, MIN_CROP, side);
    c.x = clamp(c.x, 0, iconEdit.w - c.size);
    c.y = clamp(c.y, 0, iconEdit.h - c.size);
  }

  function stageScale(): number {
    const crop = iconEdit.crop;
    if (!crop) return 1;
    return ($("crop-stage").clientWidth || 240) / crop.size;
  }

  function layoutCrop(): void {
    if (!iconEdit.url || !iconEdit.crop) { return; }
    clampCrop();
    const scale = stageScale();
    const img = $<HTMLImageElement>("crop-img");
    img.style.width = `${iconEdit.w * scale}px`;
    img.style.height = `${iconEdit.h * scale}px`;
    img.style.transform = `translate(${-iconEdit.crop.x * scale}px, ${-iconEdit.crop.y * scale}px)`;
    $<HTMLInputElement>("crop-zoom").value = String(Math.min(iconEdit.w, iconEdit.h) / iconEdit.crop.size);
    const c = iconEdit.crop;
    $("crop-stage").setAttribute("aria-label",
      `Crop area: ${Math.round(c.size)} by ${Math.round(c.size)} pixels from the ${iconEdit.w} by ${iconEdit.h} image`);
    schedulePreview();
  }

  // A short timer, not requestAnimationFrame: frames pause in hidden or throttled tabs.
  function schedulePreview(): void {
    if (previewFrame) { return; }
    previewFrame = window.setTimeout(() => {
      previewFrame = 0;
      if (!iconEdit.url || !iconEdit.img || !iconEdit.crop) { return; }
      const canvas = document.createElement("canvas");
      canvas.width = PREVIEW_SIDE;
      canvas.height = PREVIEW_SIDE;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.imageSmoothingQuality = "high";
      const c = iconEdit.crop;
      ctx.drawImage(iconEdit.img, c.x, c.y, c.size, c.size, 0, 0, PREVIEW_SIDE, PREVIEW_SIDE);
      previewUrl = canvas.toDataURL("image/png");
      $<HTMLImageElement>("crop-preview").src = previewUrl;
      updatePreview();
    }, 30);
  }

  function moveCrop(dx: number, dy: number): void {
    if (!iconEdit.crop) return;
    iconEdit.crop.x += dx;
    iconEdit.crop.y += dy;
    layoutCrop();
  }

  function zoomCrop(zoom: number): void {
    const c = iconEdit.crop;
    if (!c) return;
    const side = Math.min(iconEdit.w, iconEdit.h);
    const size = side / clamp(zoom, 1, Number($<HTMLInputElement>("crop-zoom").max));
    const cx = c.x + c.size / 2;
    const cy = c.y + c.size / 2;
    c.size = size;
    c.x = cx - size / 2;
    c.y = cy - size / 2;
    layoutCrop();
  }

  function setupCropEditor() {
    const stage = $("crop-stage");
    let drag: { x: number; y: number } | null = null;
    stage.addEventListener("pointerdown", (event) => {
      if (!iconEdit.url) { return; }
      drag = { x: event.clientX, y: event.clientY };
      stage.setPointerCapture(event.pointerId);
    });
    stage.addEventListener("pointermove", (event) => {
      if (!drag) { return; }
      const scale = stageScale();
      moveCrop(-(event.clientX - drag.x) / scale, -(event.clientY - drag.y) / scale);
      drag = { x: event.clientX, y: event.clientY };
    });
    const stop = () => { drag = null; };
    stage.addEventListener("pointerup", stop);
    stage.addEventListener("pointercancel", stop);
    stage.addEventListener("wheel", (event) => {
      if (!iconEdit.url) { return; }
      event.preventDefault();
      zoomCrop(Number($<HTMLInputElement>("crop-zoom").value) * (event.deltaY < 0 ? 1.1 : 1 / 1.1));
    }, { passive: false });
    stage.addEventListener("keydown", (event) => {
      if (!iconEdit.url) { return; }
      const step = (iconEdit.crop?.size || 0) * (event.shiftKey ? 0.1 : 0.02);
      // Arrow keys move the image (so the crop square moves the other way).
      const moves: Record<string, [number, number]> = { ArrowLeft: [step, 0], ArrowRight: [-step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] };
      const movement = moves[event.key];
      if (movement) {
        event.preventDefault();
        moveCrop(...movement);
      } else if (event.key === "+" || event.key === "=") {
        event.preventDefault();
        zoomCrop(Number($<HTMLInputElement>("crop-zoom").value) * 1.1);
      } else if (event.key === "-" || event.key === "_") {
        event.preventDefault();
        zoomCrop(Number($<HTMLInputElement>("crop-zoom").value) / 1.1);
      }
    });
    $<HTMLInputElement>("crop-zoom").addEventListener("input", () => { if (iconEdit.url) { zoomCrop(Number($<HTMLInputElement>("crop-zoom").value)); } });
    window.addEventListener("resize", layoutCrop);
    cleanups.push(() => window.removeEventListener("resize", layoutCrop));
  }

  function handleFile(file: File | null | undefined): void {
    if (!file) { return; }
    setStatus("icon-load-status", true, "Checking the image…");
    loadImageBlob(file).then(() => {
      setStatus("icon-load-status", true, "Loaded. Drag and zoom to crop it, then press Set icon.");
    }).catch((err) => setStatus("icon-load-status", false, err.message));
  }

  // A non-image reply from the icon endpoints: show why (and lock the page if access ended).
  function iconLoadProblem(status: number, body: PickerReply): void {
    const message = body.message || "Something went wrong. Try again in a moment.";
    if (status === 401) { expired(message); } else if (status === 403 && body && body.error === "not_allowed") {
      lockPage("You can't change this role right now", message);
    }
    setStatus("icon-load-status", false, message);
  }

  function loadFromServer(button: HTMLButtonElement, path: string, options: PickerRequestOptions, crop: Crop | null, success: string): void {
    if (busy || !writable) { return; }
    busy = true;
    const label = button.textContent;
    button.textContent = "Loading…";
    button.setAttribute("aria-busy", "true");
    refreshButtons();
    setStatus("icon-load-status", true, "");
    request(path, options).then((response) => {
      if (response.ok && (response.headers.get("Content-Type") || "").startsWith("image/")) {
        return response.blob().then((blob) => loadImageBlob(blob, crop)).then(() => {
          setStatus("icon-load-status", true, success);
        });
      }
      return readJson(response).then(({ status, body }) => iconLoadProblem(status, body));
    }).catch((err) => {
      setStatus("icon-load-status", false, (err && err.message) || "Can't reach the bot. Check your connection and try again.");
    }).finally(() => {
      busy = false;
      button.textContent = label;
      button.removeAttribute("aria-busy");
      refreshButtons();
    });
  }

  function showIconSource() {
    const source = iconSource();
    show($("icon-upload"), source === "upload");
    show($("icon-link"), source === "link");
    show($("icon-emoji"), source === "emoji");
    show($("crop"), source !== "emoji" && Boolean(iconEdit.url));
    if (source !== "emoji") { layoutCrop(); }
    updatePreview();
  }

  function setupIconTab() {
    all<HTMLElement>("[data-source-max]").forEach((el) => { el.textContent = formatSize(saved!.icon_source_max); });
    show($("icon-tools"), iconsUsable);
    show($("icon-unavailable"), !iconsUsable);
    all<HTMLInputElement>('input[name="icon-source"]').forEach((input) => input.addEventListener("change", showIconSource));

    const fileInput = $<HTMLInputElement>("icon-file");
    fileInput.addEventListener("change", () => {
      handleFile(fileInput.files && fileInput.files[0]);
      fileInput.value = "";
    });
    const zone = $("dropzone");
    zone.addEventListener("dragover", (event) => { event.preventDefault(); zone.classList.add("drag-over"); });
    zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
    zone.addEventListener("drop", (event) => {
      event.preventDefault();
      zone.classList.remove("drag-over");
      handleFile(event.dataTransfer && event.dataTransfer.files[0]);
    });

    $<HTMLButtonElement>("icon-load").addEventListener("click", () => {
      const url = $<HTMLInputElement>("icon-url").value.trim();
      if (!url) { setStatus("icon-load-status", false, "Paste a link first."); return; }
      loadFromServer($<HTMLButtonElement>("icon-load"), "icon/fetch", { body: { url } }, null,
        "Loaded. Drag and zoom to crop it, then press Set icon.");
    });
    $<HTMLInputElement>("icon-url").addEventListener("keydown", (event) => {
      if (event.key === "Enter") { event.preventDefault(); $<HTMLButtonElement>("icon-load").click(); }
    });

    const emojiInput = $<HTMLInputElement>("emoji-input");
    emojiInput.addEventListener("input", () => {
      iconEdit.emoji = emojiInput.value.trim();
      let note = "";
      if (iconEdit.emoji && typeof Intl !== "undefined" && Intl.Segmenter) {
        const count = Array.from(new Intl.Segmenter().segment(iconEdit.emoji)).length;
        if (count > 1) { note = "Use exactly one emoji."; }
      }
      setStatus("icon-load-status", !note, note);
      updatePreview();
    });

    $<HTMLButtonElement>("edit-crop").addEventListener("click", () => {
      const icon = saved!.role.icon;
      $<HTMLInputElement>("source-upload").checked = true;
      showIconSource();
      const crop = icon?.type === "image" ? icon.crop ?? null : null;
      loadFromServer($<HTMLButtonElement>("edit-crop"), "icon/source", {}, crop,
        "Loaded your current icon. Adjust the crop, then press Set icon.");
    });
    $<HTMLButtonElement>("set-icon").addEventListener("click", () => {
      const button = $<HTMLButtonElement>("set-icon");
      if (iconSource() === "emoji") {
        if (!iconEdit.emoji) { setStatus("status-icon", false, "Type or paste an emoji first."); return; }
        submit(button, "status-icon", "icon/emoji", { body: { emoji: iconEdit.emoji } }, "icon");
        return;
      }
      if (!iconEdit.blob) { setStatus("status-icon", false, "Choose an image or load a link first."); return; }
      clampCrop();
      const crop = iconEdit.crop;
      if (!crop) { setStatus("status-icon", false, "Load an image before setting its icon."); return; }
      const size = Math.floor(crop.size);
      const x = clamp(Math.round(crop.x), 0, iconEdit.w - size);
      const y = clamp(Math.round(crop.y), 0, iconEdit.h - size);
      const form = new FormData();
      form.append("image", iconEdit.blob, "original");
      form.append("crop", JSON.stringify({ x, y, size }));
      submit(button, "status-icon", "icon", { form }, "icon");
    });
    $<HTMLButtonElement>("remove-icon").addEventListener("click", () => {
      submit($<HTMLButtonElement>("remove-icon"), "status-icon", "icon", { method: "DELETE" }, "icon");
    });
    setupCropEditor();
    showIconSource();
  }

  // ------------------------------------------------------------------ buttons and saving

  function cooling() {
    return nextChangeAt !== null && nextChangeAt * 1000 > Date.now();
  }

  function refreshButtons() {
    all<HTMLButtonElement>("[data-set]").forEach((button) => {
      button.disabled = busy || !writable || cooling();
    });
    const icon = saved?.role.icon;
    all<HTMLButtonElement>("[data-icon-action]").forEach((button) => {
      const changes = button.id === "set-icon" || button.id === "remove-icon";
      let off = busy || !writable || (changes && cooling());
      if (button.id !== "remove-icon" && !iconsUsable) { off = true; }
      if (button.id === "edit-crop" && !(icon && icon.type === "image" && icon.has_source)) { off = true; }
      if (button.id === "remove-icon" && !icon) { off = true; }
      button.disabled = off;
    });
  }

  function setStatus(id: string, ok: boolean, message: string, notes: string[] = []): void {
    const el = $(id);
    el.className = "status " + (ok ? "status-ok" : "status-error");
    el.textContent = message || "";
    (notes || []).forEach((note) => {
      const line = make("span", "status-note");
      line.textContent = note;
      el.append(line);
    });
  }

  function applySaved(state: PickerState, part: PickerPart): void {
    saved = state;
    nextChangeAt = state.next_change_at;
    const fresh = savedEdit();
    if (part === "color") {
      edit.mode = fresh.mode;
      edit.primary = fresh.primary;
      edit.secondary = fresh.secondary || edit.secondary;
    } else if (part === "name") {
      edit.name = fresh.name;
      $<HTMLInputElement>("name-input").value = fresh.name;
      updateNameCount();
    } else if (part === "icon") {
      clearIconImage();
      iconEdit.emoji = "";
      $<HTMLInputElement>("emoji-input").value = "";
      setStatus("icon-load-status", true, "");
    }
    fields.forEach((f) => f.sync(false));
    showMode();
    showIcon();
    updatePalette();
    updatePreview();
    tickCooldown();
  }

  // Send a change and show the result. part = what the reply's state should refresh.
  function submit(button: HTMLButtonElement, statusId: string, path: string, options: PickerRequestOptions, part: PickerPart): void {
    if (busy || !writable) { return; }
    busy = true;
    const label = button.textContent;
    button.textContent = "Saving…";
    button.setAttribute("aria-busy", "true");
    refreshButtons();
    setStatus(statusId, true, "");

    api(path, options).then(({ status, body: reply }) => {
      const message = reply.message || "Something went wrong. Try again in a moment.";
      if (status === 401) { expired(message); setStatus(statusId, false, message); return; }
      if (status === 403) { lockPage("You can't change this role right now", message); setStatus(statusId, false, message); return; }
      if (status !== 200) { setStatus(statusId, false, message); return; }
      if (reply.retry_at) { nextChangeAt = reply.retry_at; tickCooldown(); }
      setStatus(statusId, reply.ok ?? false, message, reply.notes);
      if (part === "name") {
        const err = $("name-error");
        err.textContent = reply.ok ? "" : message;
        show(err, !reply.ok);
        $<HTMLInputElement>("name-input").setAttribute("aria-invalid", reply.ok ? "false" : "true");
      }
      if (reply.ok && reply.state) { applySaved(reply.state, part); }
    }).catch(() => {
      setStatus(statusId, false, "Can't reach the bot. Check your connection and try again.");
    }).finally(() => {
      busy = false;
      button.textContent = label;
      button.removeAttribute("aria-busy");
      refreshButtons();
    });
  }

  function save(kind: SaveKind, button: HTMLButtonElement): void {
    if (kind === "name") {
      submit(button, "status-name", "name", { body: { name: $<HTMLInputElement>("name-input").value } }, "name");
      return;
    }
    if (kind === "holographic") {
      submit(button, "status-holographic", "color", { body: { mode: "holographic" } }, "color");
      return;
    }
    const statusId = `status-${kind}`;
    const needed: ColorKey[] = kind === "gradient" ? ["primary", "secondary"] : ["primary"];
    const missing = needed.filter((key): key is ColorKey => !edit[key]);
    if (missing.length) {
      fields.filter((f) => missing.includes(f.key) && !f.container.closest(".hidden")).forEach((f) => f.setError(HEX_HELP));
      setStatus(statusId, false, kind === "gradient" ? "Pick both colors first." : "Pick a color first.");
      return;
    }
    const body: Record<string, unknown> = { mode: kind, primary: edit.primary };
    if (kind === "gradient") { body.secondary = edit.secondary; }
    submit(button, statusId, "color", { body }, "color");
  }

  // ------------------------------------------------------------------ timers

  let cooldownTimer: number | undefined;
  function tickCooldown() {
    window.clearTimeout(cooldownTimer);
    const note = $("cooldown-note");
    const changeAt = nextChangeAt;
    if (changeAt !== null && changeAt * 1000 > Date.now()) {
      note.textContent = `You can change your role again in ${duration(changeAt - Date.now() / 1000)}.`;
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
    const select = (tab: HTMLElement, focus: boolean): void => {
      tabs.forEach((t) => {
        const on = t === tab;
        t.setAttribute("aria-selected", on ? "true" : "false");
        t.tabIndex = on ? 0 : -1;
        const panelId = t.getAttribute("aria-controls");
        if (panelId) show($(panelId), on);
      });
      fields.forEach((f) => f.close(false));
      if (tab.id === "tab-icon") { layoutCrop(); }
      if (focus) { tab.focus(); }
    };
    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => select(tab, false));
      tab.addEventListener("keydown", (event) => {
        const moves: Record<string, number> = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: tabs.length - 1 };
        const nextIndex = moves[event.key];
        if (nextIndex === undefined) { return; }
        event.preventDefault();
        select(tabs[(nextIndex + tabs.length) % tabs.length], true);
      });
    });
  }

  function updateNameCount() {
    const input = $<HTMLInputElement>("name-input");
    $("name-count").textContent = `${input.value.length}/${input.maxLength} characters`;
  }

  function reset() {
    Object.assign(edit, savedEdit());
    $<HTMLInputElement>("name-input").value = edit.name;
    $<HTMLInputElement>("name-input").setAttribute("aria-invalid", "false");
    show($("name-error"), false);
    updateNameCount();
    clearIconImage();
    iconEdit.emoji = "";
    $<HTMLInputElement>("emoji-input").value = "";
    setStatus("icon-load-status", true, "");
    fields.forEach((f) => { f.setError(""); f.sync(false); });
    showMode();
    showIconSource();
    updatePalette();
    updatePreview();
  }

  // ------------------------------------------------------------------ start

  function render(data: { state: PickerState }): void {
    saved = data.state;
    nextChangeAt = saved.next_change_at;
    Object.assign(edit, savedEdit());

    const state = saved;
    const guild = state.guild;
    modesAllowed = Boolean(guild.gradient || guild.preview_enhanced);
    iconsUsable = Boolean(guild.icons || guild.preview_icons);
    show($("banner-debug"), Boolean(guild.preview_enhanced));
    show($("banner-debug-icons"), Boolean(guild.preview_icons));
    show($("mode-hint"), !guild.gradient);
    ["gradient", "holographic"].forEach((mode) => { $<HTMLInputElement>(`mode-${mode}`).disabled = !modesAllowed; });

    all<HTMLImageElement>("[data-avatar]").forEach((img) => {
      if (state.user.avatar_url) { img.src = state.user.avatar_url; }
    });
    const time = new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    all("[data-time]").forEach((el) => { el.textContent = `Today at ${time}`; });

    all<HTMLElement>("[data-color-field]").forEach((container) => fields.push(makeColorField(container)));
    fields.forEach((f) => f.sync(false));

    const nameInput = $<HTMLInputElement>("name-input");
    nameInput.maxLength = state.name_max || 100;
    nameInput.value = edit.name;
    updateNameCount();
    nameInput.addEventListener("input", () => {
      edit.name = nameInput.value;
      updateNameCount();
      show($("name-error"), false);
      nameInput.setAttribute("aria-invalid", "false");
      updatePreview();
    });

    all<HTMLInputElement>('input[name="mode"]').forEach((input) => input.addEventListener("change", () => {
      const value = input.value;
      if (input.checked && (value === "solid" || value === "gradient" || value === "holographic")) {
        edit.mode = value;
        showMode();
        updatePalette();
        updatePreview();
      }
    }));
    all<HTMLButtonElement>("[data-set]").forEach((button) => button.addEventListener("click", () => {
      const kind = button.dataset.set;
      if (kind === "solid" || kind === "gradient" || kind === "holographic" || kind === "name") {
        save(kind, button);
      }
    }));
    $("reset").addEventListener("click", reset);
    const handleOutsidePointerDown = (event: PointerEvent): void => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      fields.forEach((f) => {
        if (!f.pop.contains(target) && !f.button.contains(target)) { f.close(false); }
      });
    };
    const handleBeforeUnload = (event: BeforeUnloadEvent): void => {
      if (isDirty()) { event.preventDefault(); event.returnValue = ""; }
    };
    document.addEventListener("pointerdown", handleOutsidePointerDown);
    window.addEventListener("beforeunload", handleBeforeUnload);
    cleanups.push(() => document.removeEventListener("pointerdown", handleOutsidePointerDown));
    cleanups.push(() => window.removeEventListener("beforeunload", handleBeforeUnload));

    setupTabs();
    setupIconTab();
    showMode();
    showIcon();
    updatePreview();
    show($("loading"), false);
    show($("app"), true);
    tickExpiry();
    tickCooldown();

    api("palette").then(({ status, body }) => {
      const statusEl = $("palette-status");
      if (status === 200 && body.ok && body.colors?.length) {
        palette = body.colors.map(normalizeHex).filter((color): color is string => Boolean(color));
        statusEl.textContent = "Pick one to fill in the color, then press Set.";
      } else {
        statusEl.textContent = (body && body.message) || "Couldn't read colors from your avatar.";
      }
      buildPalette();
      showMode();
    }).catch(() => { $("palette-status").textContent = "Couldn't load colors from your avatar."; });
  }

  function start(): void {
    if (!token) {
      fatal("No link found", "Open this page from the Color picker button in /custom-role in Discord.");
      return;
    }
    api("state").then(({ status, body }) => {
      if (status === 200 && body.ok && body.state) { render({ state: body.state }); return; }
      const message = (body && body.message) || "Something went wrong. Try again in a moment.";
      if (status === 401) { forgetToken(); fatal("This link expired", message); return; }
      fatal("Can't open the picker", message);
    }).catch(() => fatal("Can't reach the bot", "Check your connection and reload the page."));
  }

  start();
  return () => { cleanups.splice(0).forEach((cleanup) => cleanup()); };
}
