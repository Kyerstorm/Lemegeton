// Lunar color picker. The link token arrives after '#', so it is never sent to any server
// in a URL. It is moved into this tab's sessionStorage, removed from the address bar, and
// sent only in the Authorization header.
(function () {
  "use strict";

  var STORAGE_KEY = "lunarPickerToken";

  function readToken() {
    var fromHash = window.location.hash.replace(/^#/, "");
    if (fromHash) {
      try { window.sessionStorage.setItem(STORAGE_KEY, fromHash); } catch (e) { /* storage blocked */ }
      window.history.replaceState(null, "", window.location.pathname);
      return fromHash;
    }
    try { return window.sessionStorage.getItem(STORAGE_KEY) || ""; } catch (e) { return ""; }
  }

  function forgetToken() {
    try { window.sessionStorage.removeItem(STORAGE_KEY); } catch (e) { /* storage blocked */ }
  }

  var token = readToken();

  function el(id) { return document.getElementById(id); }

  function show(id) {
    ["loading", "problem", "ready"].forEach(function (name) {
      el(name).classList.toggle("hidden", name !== id);
    });
  }

  function problem(title, text) {
    el("problem-title").textContent = title;
    el("problem-text").textContent = text;
    show("problem");
  }

  function api(path) {
    return fetch("/lunar/api/" + path, {
      headers: { "Authorization": "Bearer " + token },
      credentials: "omit",
      cache: "no-store",
      referrerPolicy: "no-referrer"
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (body) {
        return { status: response.status, body: body };
      });
    });
  }

  function styleName(nameEl, role) {
    nameEl.classList.remove("gradient-text", "holo-text");
    nameEl.style.color = "";
    nameEl.style.backgroundImage = "";
    if (role.mode === "holographic") {
      nameEl.classList.add("holo-text");
    } else if (role.mode === "gradient" && role.primary && role.secondary) {
      nameEl.classList.add("gradient-text");
      nameEl.style.backgroundImage = "linear-gradient(90deg, " + role.primary + ", " + role.secondary + ")";
    } else if (role.primary) {
      nameEl.style.color = role.primary;
    }
  }

  function describeStyle(role) {
    if (role.mode === "holographic") { return "Holographic"; }
    if (role.mode === "gradient") { return "Gradient " + role.primary + " → " + role.secondary; }
    return role.primary ? "Solid " + role.primary : "Default color";
  }

  var expiresAt = 0;

  function tickExpiry() {
    var left = Math.max(0, Math.round(expiresAt - Date.now() / 1000));
    if (left === 0) {
      forgetToken();
      problem("This link expired", "Run /lunar color-picker again for a new one.");
      return;
    }
    var minutes = Math.floor(left / 60);
    var seconds = left % 60;
    el("expires").textContent = "in " + minutes + "m " + (seconds < 10 ? "0" : "") + seconds + "s";
    window.setTimeout(tickExpiry, 1000);
  }

  function render(data) {
    var state = data.state;
    var role = state.role;
    el("avatar").src = state.user.avatar_url;
    el("display-name").textContent = state.user.name;
    styleName(el("display-name"), role);
    el("guild-name").textContent = state.guild.name;
    el("role-name").textContent = role.name || "Unnamed";
    el("role-style").textContent = describeStyle(role);

    var img = el("role-icon-img");
    var emoji = el("role-icon-emoji");
    img.classList.add("hidden");
    emoji.classList.add("hidden");
    if (role.icon && role.icon.type === "image") {
      img.src = role.icon.url;
      img.classList.remove("hidden");
    } else if (role.icon && role.icon.type === "emoji") {
      emoji.textContent = role.icon.value;
      emoji.classList.remove("hidden");
    }

    expiresAt = data.expires_at;
    show("ready");
    tickExpiry();
  }

  function start() {
    if (!token) {
      problem("No link found", "Open this page from the button that /lunar color-picker gives you in Discord.");
      return;
    }
    api("state").then(function (result) {
      if (result.status === 200 && result.body.ok) {
        render(result.body);
        return;
      }
      var message = (result.body && result.body.message) || "Something went wrong. Try again in a moment.";
      if (result.status === 401) {
        forgetToken();
        problem("This link expired", message.replace(/`/g, ""));
      } else {
        problem("Can't open the picker", message.replace(/`/g, ""));
      }
    }).catch(function () {
      problem("Can't reach the bot", "Check your connection and reload the page.");
    });
  }

  document.addEventListener("DOMContentLoaded", start);
}());
