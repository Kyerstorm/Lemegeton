import { describe, expect, it } from "vitest";
import {
  clamp,
  contrast,
  duration,
  formatSize,
  hexToRgb,
  hsvToRgb,
  luminance,
  normalizeHex,
  rgbToHex,
  rgbToHsv,
} from "../../src/Components/Features/CustomRoles/picker-utils";
import {
  isValidRoleIconCrop,
  roleIconDimensionError,
  validateRoleIconImageHeader,
} from "../../src/Components/Features/CustomRoles/UploadValidation";

function pngHeader(width: number, height: number): Uint8Array {
  const bytes = new Uint8Array(24);
  bytes.set([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a], 0);
  bytes.set([0x49, 0x48, 0x44, 0x52], 12);
  const view = new DataView(bytes.buffer);
  view.setUint32(16, width);
  view.setUint32(20, height);
  return bytes;
}

describe("Custom Roles colour utilities", () => {
  it("normalizes supported short and long hex values", () => {
    expect(normalizeHex(" #abc ")).toBe("#AABBCC");
    expect(normalizeHex("a1b2c3")).toBe("#A1B2C3");
    expect(normalizeHex("#000000")).toBe("#010101");
    expect(normalizeHex("#12xz90")).toBeNull();
    expect(normalizeHex(undefined)).toBeNull();
  });

  it("converts RGB and HSV without changing the represented colour", () => {
    expect(hexToRgb("#0C2238")).toEqual([12, 34, 56]);
    expect(rgbToHex([12, 34, 56])).toBe("#0C2238");
    const original = [255, 128, 0] as const;
    expect(hsvToRgb(rgbToHsv(original)).map(Math.round)).toEqual(original);
  });

  it("calculates contrast and clamps values at both bounds", () => {
    expect(luminance("#FFFFFF")).toBeCloseTo(1, 10);
    expect(luminance("#000000")).toBe(0);
    expect(contrast("#FFFFFF", "#000000")).toBeCloseTo(21, 8);
    expect(clamp(-4, 0, 100)).toBe(0);
    expect(clamp(140, 0, 100)).toBe(100);
    expect(clamp(32, 0, 100)).toBe(32);
  });

  it("formats cooldowns and upload sizes consistently", () => {
    expect(duration(90)).toBe("1m 30s");
    expect(duration(86_461)).toBe("1d 1m 1s");
    expect(duration(-5)).toBe("0s");
    expect(formatSize(2_048)).toBe("2 KB");
    expect(formatSize(1_048_576)).toBe("1 MB");
  });
});

describe("Custom Roles image upload validation", () => {
  it("reads PNG dimensions from the IHDR header", () => {
    expect(validateRoleIconImageHeader(pngHeader(128, 64), 24, 1024)).toEqual({
      width: 128,
      height: 64,
      format: "png",
    });
  });

  it("reads JPEG dimensions from a baseline frame header", () => {
    const jpeg = new Uint8Array([
      0xff, 0xd8, 0xff, 0xc0, 0x00, 0x08, 0x08, 0x00, 0x20, 0x00, 0x30, 0x00,
    ]);
    expect(validateRoleIconImageHeader(jpeg, jpeg.length, 1024)).toEqual({
      width: 48,
      height: 32,
      format: "jpeg",
    });
  });

  it("rejects unsupported, HEIC, damaged and oversized files before decoding", () => {
    expect(() => validateRoleIconImageHeader(new Uint8Array([0x47, 0x49, 0x46]), 3, 1024))
      .toThrow(/Only PNG or JPEG/);

    const heic = new Uint8Array(16);
    new DataView(heic.buffer).setUint32(0, 16);
    heic.set([0x66, 0x74, 0x79, 0x70], 4);
    heic.set([0x68, 0x65, 0x69, 0x63], 8);
    expect(() => validateRoleIconImageHeader(heic, heic.length, 1024))
      .toThrow(/HEIC photos aren't supported/);

    expect(() => validateRoleIconImageHeader(
      new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
      8,
      1024,
    )).toThrow(/damaged/);
    expect(() => validateRoleIconImageHeader(pngHeader(1, 1), 2048, 1024))
      .toThrow(/2 KB.*1 KB/);
    expect(() => validateRoleIconImageHeader(pngHeader(1, 1), -1, 1024))
      .toThrow(TypeError);
  });

  it("rejects excessive dimensions while allowing images within the limits", () => {
    expect(roleIconDimensionError(4000, 4000)).toBeNull();
    expect(roleIconDimensionError(4096, 4096)).toContain("limit is 16 million pixels");
    expect(roleIconDimensionError(8193, 1)).toContain("8193 px wide");
    expect(roleIconDimensionError(1, 0)).toContain("damaged");
    expect(() => validateRoleIconImageHeader(pngHeader(4096, 4096), 24, 1024))
      .toThrow(/limit is 16 million pixels/);
  });

  it("accepts only integer square crops fully contained in the source image", () => {
    expect(isValidRoleIconCrop({ x: 8, y: 12, size: 16 }, 100, 80)).toBe(true);
    expect(isValidRoleIconCrop({ x: 84, y: 64, size: 16 }, 100, 80)).toBe(true);
    expect(isValidRoleIconCrop({ x: 85, y: 64, size: 16 }, 100, 80)).toBe(false);
    expect(isValidRoleIconCrop({ x: 0, y: 0, size: 15 }, 100, 80)).toBe(false);
    expect(isValidRoleIconCrop({ x: 0.5, y: 0, size: 16 }, 100, 80)).toBe(false);
    expect(isValidRoleIconCrop(null, 100, 80)).toBe(false);
  });
});
