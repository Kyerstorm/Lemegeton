import assert from "node:assert/strict";
import test from "node:test";
import {
  isValidRoleIconCrop,
  roleIconDimensionError,
  validateRoleIconImageHeader,
} from "../web/frontend/src/Components/Features/CustomRoles/UploadValidation.ts";

function png(width: number, height: number): Uint8Array {
  const bytes = new Uint8Array(24);
  bytes.set([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  bytes.set([0x49, 0x48, 0x44, 0x52], 12);
  new DataView(bytes.buffer).setUint32(16, width);
  new DataView(bytes.buffer).setUint32(20, height);
  return bytes;
}

function jpeg(width: number, height: number): Uint8Array {
  return new Uint8Array([
    0xff, 0xd8,
    0xff, 0xc0, 0x00, 0x08, 0x08,
    (height >>> 8) & 0xff, height & 0xff,
    (width >>> 8) & 0xff, width & 0xff,
    0x01,
  ]);
}

function heif(): Uint8Array {
  return new Uint8Array([
    0x00, 0x00, 0x00, 0x18, 0x66, 0x74, 0x79, 0x70,
    0x68, 0x65, 0x69, 0x63, 0x00, 0x00, 0x00, 0x00,
    0x68, 0x65, 0x69, 0x63, 0x00, 0x00, 0x00, 0x00,
  ]);
}

test("accepts PNG dimensions from the file signature and IHDR header", () => {
  assert.deepEqual(validateRoleIconImageHeader(png(512, 256), 24, 1_000), {
    width: 512,
    height: 256,
    format: "png",
  });
});

test("accepts JPEG dimensions from a bounded start-of-frame segment", () => {
  assert.deepEqual(validateRoleIconImageHeader(jpeg(640, 480), 12, 1_000), {
    width: 640,
    height: 480,
    format: "jpeg",
  });
});

test("rejects a file that exceeds the server-provided byte cap", () => {
  assert.throws(() => validateRoleIconImageHeader(png(10, 10), 2_000, 1_000), /Images can be at most/);
});

test("rejects HEIF with a useful conversion message", () => {
  assert.throws(() => validateRoleIconImageHeader(heif(), 24, 1_000), /HEIC photos aren't supported/);
});

test("rejects non-image, truncated and malformed JPEG headers", () => {
  assert.throws(() => validateRoleIconImageHeader(new Uint8Array([1, 2, 3]), 3, 1_000), /Only PNG or JPEG/);
  assert.throws(() => validateRoleIconImageHeader(png(1, 1).slice(0, 16), 16, 1_000), /damaged/);
  assert.throws(() => validateRoleIconImageHeader(new Uint8Array([0xff, 0xd8, 0xff, 0xc0, 0, 1]), 6, 1_000), /damaged/);
});

test("rejects decompression-bomb dimensions before image decoding", () => {
  assert.throws(() => validateRoleIconImageHeader(png(16_000, 16_000), 24, 1_000), /million pixels/);
  assert.match(roleIconDimensionError(9_000, 100) ?? "", /9000 px wide/);
  assert.match(roleIconDimensionError(0, 100) ?? "", /damaged/);
});

test("rejects invalid or out-of-bounds crop rectangles", () => {
  assert.equal(isValidRoleIconCrop({ x: 0, y: 0, size: 64 }, 128, 128), true);
  assert.equal(isValidRoleIconCrop({ x: -1, y: 0, size: 64 }, 128, 128), false);
  assert.equal(isValidRoleIconCrop({ x: 0, y: 0, size: 16 }, 8, 8), false);
});
