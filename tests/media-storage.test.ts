import assert from "node:assert/strict";
import test from "node:test";
import sharp from "sharp";
import { stripArchiveImageMetadata } from "../helpers/media/media-storage.js";

test("Archive image storage removes EXIF metadata before retaining an image", async () => {
  const original = await sharp({
    create: {
      width: 48,
      height: 32,
      channels: 3,
      background: { r: 120, g: 150, b: 180 },
    },
  })
    .jpeg()
    .withExif({ IFD0: { ImageDescription: "private location details" } })
    .toBuffer();

  assert.ok((await sharp(original).metadata()).exif);

  const sanitized = await stripArchiveImageMetadata(original, "image/jpeg");
  const metadata = await sharp(sanitized).metadata();

  assert.equal(metadata.format, "jpeg");
  assert.equal(metadata.exif, undefined);
  assert.equal(metadata.iptc, undefined);
  assert.equal(metadata.xmp, undefined);
});

test("Archive image storage rejects content that does not match its declared format", async () => {
  const png = await sharp({
    create: {
      width: 16,
      height: 16,
      channels: 4,
      background: { r: 80, g: 90, b: 100, alpha: 1 },
    },
  }).png().toBuffer();

  await assert.rejects(
    stripArchiveImageMetadata(png, "image/jpeg"),
    /contents do not match/,
  );
});
