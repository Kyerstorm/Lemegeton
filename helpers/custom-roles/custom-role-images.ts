import sharp, { type Metadata } from "sharp";

export const CUSTOM_ROLE_ICON_MAX_SOURCE_BYTES = Math.max(
  256 * 1024,
  Number.isSafeInteger(Number(process.env.CUSTOM_ROLES_ICON_SOURCE_MAX_BYTES))
    ? Number(process.env.CUSTOM_ROLES_ICON_SOURCE_MAX_BYTES)
    : 8 * 1024 * 1024,
);
export const CUSTOM_ROLE_ICON_MAX_SIDE = 8192;
export const CUSTOM_ROLE_ICON_MAX_PIXELS = 16_000_000;
export const CUSTOM_ROLE_ICON_MAX_OUTPUT_BYTES = 256 * 1024;
export const CUSTOM_ROLE_ICON_SIZES = [256, 128, 64] as const;
export const CUSTOM_ROLE_ICON_MIN_CROP = 16;

export interface CustomRoleIconCrop {
  x: number;
  y: number;
  size: number;
}

export interface ProcessedCustomRoleIcon {
  png: Buffer;
  side: number;
  crop: CustomRoleIconCrop;
  sourceType: "png" | "jpeg";
  width: number;
  height: number;
}

function imageKind(bytes: Buffer): "png" | "jpeg" | null {
  if (bytes.byteLength >= 8 && bytes.subarray(0, 8).equals(Buffer.from([0x89,0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a]))) return "png";
  if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) return "jpeg";
  return null;
}

function isHeif(bytes: Buffer): boolean {
  if (bytes.length < 12 || bytes.toString("ascii", 4, 8) !== "ftyp") return false;
  const boxEnd = Math.min(Math.max(bytes.readUInt32BE(0), 16), 256, bytes.length);
  const brands = [bytes.toString("ascii", 8, 12)];
  for (let offset = 16; offset + 4 <= boxEnd; offset += 4) brands.push(bytes.toString("ascii", offset, offset + 4));
  return !brands.includes("avif") && !brands.includes("avis")
    && brands.some(brand => ["heic","heix","hevc","hevx","heim","heis","hevm","hevs","mif1","msf1"].includes(brand));
}

function validateCrop(crop: CustomRoleIconCrop | undefined, width: number, height: number): CustomRoleIconCrop {
  if (!crop) {
    const size = Math.min(width, height);
    return { x: Math.floor((width - size) / 2), y: Math.floor((height - size) / 2), size };
  }
  const { x, y, size } = crop;
  if (![x, y, size].every(Number.isSafeInteger) || size < CUSTOM_ROLE_ICON_MIN_CROP
    || x < 0 || y < 0 || x + size > width || y + size > height) {
    throw new Error("That crop doesn't fit inside the image. Choose a square of at least 16 pixels within the image.");
  }
  return { x, y, size };
}

export async function processCustomRoleIconImage(
  input: Buffer,
  crop?: CustomRoleIconCrop,
): Promise<ProcessedCustomRoleIcon> {
  if (input.byteLength < 1) throw new Error("The role icon image is empty.");
  if (input.byteLength > CUSTOM_ROLE_ICON_MAX_SOURCE_BYTES) {
    throw new Error("That image is too large. The original upload limit is "
      + Math.ceil(CUSTOM_ROLE_ICON_MAX_SOURCE_BYTES / (1024 * 1024)) + " MB.");
  }
  const sourceType = imageKind(input);
  if (!sourceType) {
    if (isHeif(input)) throw new Error("iPhone HEIC/HEIF images are not supported. Save it as JPEG or PNG and try again.");
    throw new Error("Only real PNG or JPEG images can be used as role icons.");
  }

  let metadata: Metadata;
  try {
    metadata = await sharp(input, { limitInputPixels: CUSTOM_ROLE_ICON_MAX_PIXELS, animated: true }).metadata();
  } catch {
    throw new Error("I couldn't read that image. It may be damaged or exceed the pixel safety limit.");
  }
  if (metadata.format !== sourceType) throw new Error("The file contents do not match a supported PNG or JPEG image.");
  if (sourceType === "png" && (metadata.pages ?? 1) > 1) {
    throw new Error("Animated PNG images cannot be used as role icons. Use a still PNG or JPEG.");
  }
  const rawWidth = metadata.width;
  const rawHeight = metadata.height;
  if (!rawWidth || !rawHeight) throw new Error("The image dimensions could not be read.");
  const rotated = [5, 6, 7, 8].includes(metadata.orientation ?? 1);
  const width = rotated ? rawHeight : rawWidth;
  const height = rotated ? rawWidth : rawHeight;
  if (width > CUSTOM_ROLE_ICON_MAX_SIDE || height > CUSTOM_ROLE_ICON_MAX_SIDE) {
    throw new Error("The image exceeds the 8192 pixel per-side limit.");
  }
  if (width * height > CUSTOM_ROLE_ICON_MAX_PIXELS) {
    throw new Error("The image exceeds the 16 million pixel safety limit.");
  }

  const selectedCrop = validateCrop(crop, width, height);
  const targets = CUSTOM_ROLE_ICON_SIZES.filter(side => side <= selectedCrop.size);
  if (!targets.length) targets.push(64);

  for (const side of targets) {
    const png = await sharp(input, { limitInputPixels: CUSTOM_ROLE_ICON_MAX_PIXELS })
      .rotate()
      .extract({
        left: selectedCrop.x,
        top: selectedCrop.y,
        width: selectedCrop.size,
        height: selectedCrop.size,
      })
      .resize(side, side, { fit: "fill", kernel: sharp.kernel.lanczos3 })
      .png({ compressionLevel: 9, adaptiveFiltering: true })
      .toBuffer();
    if (png.byteLength <= CUSTOM_ROLE_ICON_MAX_OUTPUT_BYTES) {
      return { png, side, crop: selectedCrop, sourceType, width, height };
    }
  }
  throw new Error("That image is still too large after resizing. Try a simpler image or a smaller crop.");
}

export async function extractCustomRoleAvatarPalette(input: Buffer, maxColors = 25): Promise<number[]> {
  if (!input.byteLength || input.byteLength > 2 * 1024 * 1024) return [];
  const { data, info } = await sharp(input, { limitInputPixels: 4_000_000 })
    .rotate()
    .resize(64, 64, { fit: "inside", withoutEnlargement: true })
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
  const counts = new Map<number, { count: number; r: number; g: number; b: number }>();
  for (let offset = 0; offset < data.length; offset += info.channels) {
    const alpha = data[offset + 3] ?? 0;
    if (alpha < 64) continue;
    const r = data[offset] ?? 0, g = data[offset + 1] ?? 0, b = data[offset + 2] ?? 0;
    const key = ((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3);
    const current = counts.get(key) ?? { count: 0, r: 0, g: 0, b: 0 };
    current.count += 1; current.r += r; current.g += g; current.b += b;
    counts.set(key, current);
  }
  const candidates = [...counts.values()]
    .sort((a, b) => b.count - a.count)
    .map(item => ({
      count: item.count,
      r: Math.round(item.r / item.count),
      g: Math.round(item.g / item.count),
      b: Math.round(item.b / item.count),
    }));
  const result: number[] = [];
  for (const candidate of candidates) {
    if (result.some(color => {
      const r = (color >> 16) & 255, g = (color >> 8) & 255, b = color & 255;
      return Math.hypot(candidate.r - r, candidate.g - g, candidate.b - b) < 30;
    })) continue;
    result.push((candidate.r << 16) | (candidate.g << 8) | candidate.b);
    if (result.length >= Math.min(25, Math.max(1, maxColors))) break;
  }
  return result;
}
