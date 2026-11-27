export type RGB = readonly [red: number, green: number, blue: number];

export interface HSV {
  h: number;
  s: number;
  v: number;
}

export function duration(seconds: number): string {
  let remaining = Math.max(0, Math.round(seconds));
  const parts: string[] = [];

  const units: ReadonlyArray<readonly [number, string]> = [
    [86_400, "d"],
    [3_600, "h"],
    [60, "m"],
    [1, "s"],
  ];

  for (const [size, unit] of units) {
    if (remaining >= size) {
      parts.push(Math.floor(remaining / size) + unit);
      remaining %= size;
    }
  }

  return parts.join(" ") || "0s";
}

export function formatSize(bytes: number): string {
  return bytes >= 1_048_576
    ? `${(bytes / 1_048_576).toFixed(1).replace(/\.0$/, "")} MB`
    : `${Math.max(1, Math.floor(bytes / 1_024))} KB`;
}

export function clamp(value: number, low: number, high: number): number {
  return Math.min(high, Math.max(low, value));
}

// Match the bot's accepted #RRGGBB, RRGGBB, #RGB and RGB formats.
export function normalizeHex(input: unknown): string | null {
  let value = String(input || "").trim().replace(/^#/, "");

  if (/^[0-9a-f]{3}$/i.test(value)) {
    value = value.replace(/./g, character => character + character);
  }

  if (!/^[0-9a-f]{6}$/i.test(value)) return null;

  value = value.toUpperCase();
  return "#" + (value === "000000" ? "010101" : value);
}

export function hexToRgb(hex: string): RGB {
  return [
    Number.parseInt(hex.slice(1, 3), 16),
    Number.parseInt(hex.slice(3, 5), 16),
    Number.parseInt(hex.slice(5, 7), 16),
  ];
}

export function rgbToHex([red, green, blue]: RGB): string | null {
  return normalizeHex(
    [red, green, blue]
      .map(channel => Math.round(channel).toString(16).padStart(2, "0"))
      .join(""),
  );
}

export function rgbToHsv([red, green, blue]: RGB): HSV {
  const r = red / 255;
  const g = green / 255;
  const b = blue / 255;
  const max = Math.max(r, g, b);
  const difference = max - Math.min(r, g, b);

  let h = 0;

  if (difference) {
    if (max === r) {
      h = ((g - b) / difference) % 6;
    } else if (max === g) {
      h = (b - r) / difference + 2;
    } else {
      h = (r - g) / difference + 4;
    }

    h = (h * 60 + 360) % 360;
  }

  return { h, s: max ? difference / max : 0, v: max };
}

export function hsvToRgb({ h, s, v }: HSV): RGB {
  const channel = (offset: number): number => {
    const k = (offset + h / 60) % 6;
    return (v - v * s * Math.max(0, Math.min(k, 4 - k, 1))) * 255;
  };

  return [channel(5), channel(3), channel(1)];
}

function linearize(channel: number): number {
  const normalized = channel / 255;
  return normalized <= 0.03928
    ? normalized / 12.92
    : ((normalized + 0.055) / 1.055) ** 2.4;
}

export function luminance(hex: string): number {
  const [red, green, blue] = hexToRgb(hex);

  return (
    0.2126 * linearize(red) +
    0.7152 * linearize(green) +
    0.0722 * linearize(blue)
  );
}

export function contrast(first: string, second: string): number {
  const firstLuminance = luminance(first);
  const secondLuminance = luminance(second);
  const high = Math.max(firstLuminance, secondLuminance);
  const low = Math.min(firstLuminance, secondLuminance);

  return (high + 0.05) / (low + 0.05);
}
