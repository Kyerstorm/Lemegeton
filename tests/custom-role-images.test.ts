import test from "node:test";
import assert from "node:assert/strict";
import sharp from "sharp";
import {
  CUSTOM_ROLE_ICON_MAX_SOURCE_BYTES,
  extractCustomRoleAvatarPalette,
  processCustomRoleIconImage,
} from "../helpers/custom-roles/custom-role-images.js";

async function pngFixture(width = 32, height = 24): Promise<Buffer> {
  return sharp({
    create: {
      width,
      height,
      channels: 4,
      background: { r: 90, g: 120, b: 180, alpha: 1 },
    },
  }).png().toBuffer();
}

test("role icon processing accepts PNG and creates a centered square output", async () => {
  const input = await pngFixture();
  const result = await processCustomRoleIconImage(input);

  assert.equal(result.sourceType, "png");
  assert.equal(result.width, 32);
  assert.equal(result.height, 24);
  assert.deepEqual(result.crop, { x: 4, y: 0, size: 24 });
  assert.equal(result.side, 64);
  assert.ok(result.png.byteLength <= 256 * 1024);
  assert.equal((await sharp(result.png).metadata()).format, "png");
});

test("role icon processing accepts JPEG and applies a requested crop", async () => {
  const input = await sharp({
    create: {
      width: 64,
      height: 48,
      channels: 3,
      background: { r: 220, g: 150, b: 80 },
    },
  }).jpeg().toBuffer();

  const result = await processCustomRoleIconImage(input, { x: 8, y: 4, size: 32 });
  assert.equal(result.sourceType, "jpeg");
  assert.deepEqual(result.crop, { x: 8, y: 4, size: 32 });
  assert.equal(result.side, 64);
});

test("role icon processing rejects empty, unsupported and malformed image data", async () => {
  await assert.rejects(processCustomRoleIconImage(Buffer.alloc(0)), /image is empty/);
  await assert.rejects(processCustomRoleIconImage(Buffer.from("not an image")), /Only real PNG or JPEG/);
  await assert.rejects(
    processCustomRoleIconImage(Buffer.concat([
      Buffer.from([0x89,0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a]),
      Buffer.from("broken"),
    ])),
    /damaged|safety limit/,
  );
});

test("role icon processing rejects HEIF signatures with a conversion hint", async () => {
  const heif = Buffer.alloc(24);
  heif.writeUInt32BE(24, 0);
  heif.write("ftyp", 4, "ascii");
  heif.write("heic", 8, "ascii");
  heif.write("heic", 16, "ascii");
  await assert.rejects(processCustomRoleIconImage(heif), /HEIC\/HEIF/);
});

test("role icon processing enforces source size and crop bounds", async () => {
  await assert.rejects(
    processCustomRoleIconImage(Buffer.alloc(CUSTOM_ROLE_ICON_MAX_SOURCE_BYTES + 1)),
    /image is too large/,
  );
  const input = await pngFixture(32, 32);
  await assert.rejects(processCustomRoleIconImage(input, { x: 24, y: 0, size: 16 }), /crop doesn't fit/);
  await assert.rejects(processCustomRoleIconImage(input, { x: 0, y: 0, size: 15 }), /at least 16 pixels/);
});

test("avatar palette extraction returns distinct colors and ignores invalid input", async () => {
  assert.deepEqual(await extractCustomRoleAvatarPalette(Buffer.alloc(0)), []);
  const input = await pngFixture(64, 64);
  const palette = await extractCustomRoleAvatarPalette(input, 5);
  assert.ok(palette.length >= 1);
  assert.ok(palette.length <= 5);
  assert.ok(palette.every(color => Number.isSafeInteger(color) && color >= 0 && color <= 0xffffff));
});
