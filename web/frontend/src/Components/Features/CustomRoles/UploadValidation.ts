export interface ImageDimensions {
  width: number;
  height: number;
}

export interface RoleIconImageHeader extends ImageDimensions {
  format: "png" | "jpeg";
}

const PNG_SIGNATURE = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a] as const;
const MAX_IMAGE_SIDE = 8192;
const MAX_IMAGE_PIXELS = 16_000_000;
const MAX_HEADER_BYTES = 256 * 1024;
const MIN_CROP = 16;
const HEIC_MESSAGE = "iPhone HEIC photos aren't supported. Save it as JPEG or PNG (or take a screenshot) and try again.";
const HEIF_BRANDS = new Set(["heic", "heix", "hevc", "hevx", "heim", "heis", "hevm", "hevs", "mif1", "msf1"]);

function formatSize(bytes: number): string {
  return bytes >= 1_048_576
    ? `${(bytes / 1_048_576).toFixed(1).replace(/\.0$/, "")} MB`
    : `${Math.max(1, Math.floor(bytes / 1_024))} KB`;
}

function exifOrientation(bytes: Uint8Array, view: DataView, start: number, end: number): number {
  const signature = [0x45, 0x78, 0x69, 0x66, 0, 0];
  if (end - start < 16 || !signature.every((byte, index) => bytes[start + index] === byte)) return 0;

  const tiff = start + 6;
  const littleEndian = bytes[tiff] === 0x49 && bytes[tiff + 1] === 0x49;
  const bigEndian = bytes[tiff] === 0x4d && bytes[tiff + 1] === 0x4d;
  if (!littleEndian && !bigEndian) return 0;
  if (view.getUint16(tiff + 2, littleEndian) !== 42) return 0;

  const offset = view.getUint32(tiff + 4, littleEndian);
  const ifd = tiff + offset;
  if (!Number.isSafeInteger(ifd) || ifd < tiff + 8 || ifd + 2 > end) return 0;

  const count = view.getUint16(ifd, littleEndian);
  for (let index = 0; index < count && ifd + 2 + (index + 1) * 12 <= end; index++) {
    const entry = ifd + 2 + index * 12;
    if (view.getUint16(entry, littleEndian) === 0x0112) {
      return view.getUint16(entry + 8, littleEndian);
    }
  }
  return 0;
}

function pngDimensions(bytes: Uint8Array, view: DataView): ImageDimensions | null {
  if (bytes.length < 24 || String.fromCharCode(...bytes.subarray(12, 16)) !== "IHDR") return null;
  const width = view.getUint32(16);
  const height = view.getUint32(20);
  return width > 0 && height > 0 ? { width, height } : null;
}

function jpegDimensions(bytes: Uint8Array, view: DataView): ImageDimensions | null {
  let rotated = false;
  let offset = 2;

  while (offset + 4 <= bytes.length) {
    if (bytes[offset] !== 0xff) {
      offset++;
      continue;
    }

    const marker = bytes[offset + 1];
    if (marker === undefined) return null;
    if (marker === 0xff) {
      offset++;
      continue;
    }
    if (marker === 0xd8 || marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7)) {
      offset += 2;
      continue;
    }
    if (offset + 4 > bytes.length) return null;

    const segmentLength = view.getUint16(offset + 2);
    if (segmentLength < 2 || offset + 2 + segmentLength > bytes.length) return null;
    const segmentEnd = offset + 2 + segmentLength;

    if (marker === 0xe1) {
      rotated ||= [5, 6, 7, 8].includes(exifOrientation(bytes, view, offset + 4, segmentEnd));
    }

    if (marker >= 0xc0 && marker <= 0xcf && marker !== 0xc4 && marker !== 0xc8 && marker !== 0xcc) {
      if (segmentLength < 8) return null;
      const height = view.getUint16(offset + 5);
      const width = view.getUint16(offset + 7);
      if (!width || !height) return null;
      return rotated ? { width: height, height: width } : { width, height };
    }
    offset = segmentEnd;
  }
  return null;
}

function isHeif(bytes: Uint8Array): boolean {
  if (bytes.length < 12 || String.fromCharCode(...bytes.subarray(4, 8)) !== "ftyp") return false;
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const boxSize = view.getUint32(0);
  const boxEnd = Math.min(Math.max(boxSize, 16), 256, bytes.length);
  const brands = [String.fromCharCode(...bytes.subarray(8, 12))];
  for (let offset = 16; offset + 4 <= boxEnd; offset += 4) {
    brands.push(String.fromCharCode(...bytes.subarray(offset, offset + 4)));
  }
  return !brands.some(brand => brand === "avif" || brand === "avis")
    && brands.some(brand => HEIF_BRANDS.has(brand));
}

export function roleIconDimensionError(width: number, height: number): string | null {
  if (!Number.isSafeInteger(width) || !Number.isSafeInteger(height) || width <= 0 || height <= 0) {
    return "I couldn't read that image. It may be damaged.";
  }

  const overTotal = width * height > MAX_IMAGE_PIXELS;
  if (overTotal) {
    const millions = Math.ceil(width * height / 100_000) / 10;
    return `This image is ${width}x${height} px (${millions} million pixels); the limit is 16 million pixels. Try a 12 MP photo or a screenshot.`;
  }

  let message: string;
  if (width > MAX_IMAGE_SIDE && height > MAX_IMAGE_SIDE) {
    message = `This image is ${width}x${height} px; the limit is ${MAX_IMAGE_SIDE} px per side.`;
  } else if (height > MAX_IMAGE_SIDE) {
    message = `This image is ${height} px tall; the limit is ${MAX_IMAGE_SIDE} px per side.`;
  } else if (width > MAX_IMAGE_SIDE) {
    message = `This image is ${width} px wide; the limit is ${MAX_IMAGE_SIDE} px per side.`;
  } else {
    return null;
  }
  return message;
}

/** Validates image bytes and dimensions before handing a blob to the browser decoder. */
export function validateRoleIconImageHeader(
  bytes: Uint8Array,
  fileSize: number,
  maxBytes: number,
): RoleIconImageHeader {
  if (!Number.isSafeInteger(fileSize) || fileSize < 0 || !Number.isSafeInteger(maxBytes) || maxBytes < 1) {
    throw new TypeError("Invalid image size limits.");
  }
  if (fileSize > maxBytes) {
    throw new Error(`That image is ${formatSize(fileSize)}. Images can be at most ${formatSize(maxBytes)}.`);
  }

  const head = bytes.subarray(0, MAX_HEADER_BYTES);
  const isPng = head.length >= PNG_SIGNATURE.length
    && PNG_SIGNATURE.every((byte, index) => head[index] === byte);
  const isJpeg = head[0] === 0xff && head[1] === 0xd8 && head[2] === 0xff;
  if (!isPng && !isJpeg) {
    throw new Error(isHeif(head)
      ? HEIC_MESSAGE
      : "Only PNG or JPEG images work as role icons (checked by the file's content, not its name).");
  }

  const view = new DataView(head.buffer, head.byteOffset, head.byteLength);
  const dimensions = isPng ? pngDimensions(head, view) : jpegDimensions(head, view);
  if (!dimensions) throw new Error("I couldn't read that image. It may be damaged.");

  const dimensionError = roleIconDimensionError(dimensions.width, dimensions.height);
  if (dimensionError) throw new Error(dimensionError);
  return { ...dimensions, format: isPng ? "png" : "jpeg" };
}

export function isValidRoleIconCrop(
  crop: { x: number; y: number; size: number } | null | undefined,
  width: number,
  height: number,
): crop is { x: number; y: number; size: number } {
  return crop !== null && crop !== undefined
    && [crop.x, crop.y, crop.size].every(Number.isSafeInteger)
    && crop.size >= MIN_CROP
    && crop.x >= 0
    && crop.y >= 0
    && crop.x + crop.size <= width
    && crop.y + crop.size <= height;
}
