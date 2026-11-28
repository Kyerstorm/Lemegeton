"use client";

import { useEffect } from "react";
import { ALL_SOUND_ROLES, type SoundRole } from "../DesignSystem/SensoryUI/config/sound-roles";
import { useSensoryUI } from "../DesignSystem/SensoryUI/config/provider";

const soundRoles = new Set<string>(ALL_SOUND_ROLES);

const interactiveSelector = [
  "button:not(:disabled):not([aria-disabled='true'])",
  "a[href]:not([aria-disabled='true'])",
  "select:not(:disabled)",
  "input[type='checkbox']:not(:disabled)",
  "input[type='radio']:not(:disabled)",
  "input[type='range']:not(:disabled)",
  "input[type='button']:not(:disabled)",
  "input[type='submit']:not(:disabled)",
  "input[type='reset']:not(:disabled)",
  "[role='button']:not([aria-disabled='true'])",
  "[role='switch']:not([aria-disabled='true'])",
  "[role='checkbox']:not([aria-disabled='true'])",
  "[role='radio']:not([aria-disabled='true'])",
  "[role='tab']:not([aria-disabled='true'])",
  "[role='menuitem']:not([aria-disabled='true'])",
  "[role='menuitemcheckbox']:not([aria-disabled='true'])",
  "[role='menuitemradio']:not([aria-disabled='true'])",
  "[role='option']:not([aria-disabled='true'])",
  "[role='combobox']:not([aria-disabled='true'])",
  "[data-sound-interactive]",
].join(",");

function resolveSoundRole(control: HTMLElement): SoundRole | null {
  if (
    control.hasAttribute("disabled") ||
    control.getAttribute("aria-disabled") === "true" ||
    control.closest(".hold-confirm-button, [data-sound-disabled]")
  ) {
    return null;
  }

  const explicitRole = control.getAttribute("data-sound");
  if (explicitRole === "none") return null;
  if (explicitRole) {
    return soundRoles.has(explicitRole) ? explicitRole as SoundRole : null;
  }

  const role = control.getAttribute("role");
  if (role === "tab") return "navigation.tab";

  if (
    role === "switch" ||
    role === "checkbox" ||
    role === "radio" ||
    role === "menuitemcheckbox" ||
    role === "menuitemradio" ||
    role === "option"
  ) {
    return "interaction.toggle";
  }

  if (
    (control instanceof HTMLButtonElement &&
      (control.hasAttribute("aria-haspopup") || control.hasAttribute("aria-expanded"))) ||
    role === "combobox"
  ) {
    return control.getAttribute("aria-expanded") === "true"
      ? "overlay.close"
      : "overlay.open";
  }

  if (control instanceof HTMLInputElement && (control.type === "checkbox" || control.type === "radio")) {
    return "interaction.toggle";
  }

  if (control instanceof HTMLSelectElement) return "interaction.toggle";
  if (control instanceof HTMLAnchorElement) return "navigation.forward";
  if (control.hasAttribute("aria-pressed")) return "interaction.toggle";

  return "interaction.tap";
}

export function SensoryInteractions() {
  const { playSound } = useSensoryUI();

  useEffect(() => {
    const handleInteraction = (event: MouseEvent) => {
      if (!event.isTrusted || !(event.target instanceof Element)) return;

      const control = event.target.closest<HTMLElement>(interactiveSelector);
      if (!control) return;

      const role = resolveSoundRole(control);
      if (role) void playSound(role, { volume: 0.75 });
    };

    document.addEventListener("click", handleInteraction, true);
    return () => document.removeEventListener("click", handleInteraction, true);
  }, [playSound]);

  return null;
}
