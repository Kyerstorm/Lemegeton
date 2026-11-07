import { lookup as dnsLookup } from "node:dns/promises";
import type { LookupAddress, LookupFunction } from "node:dns";
import { isIP } from "node:net";
import https from "node:https";

function publicIpv4(address: string): boolean {
  const parts = address.split(".").map(Number);
  if (parts.length !== 4 || parts.some(value => !Number.isInteger(value) || value < 0 || value > 255)) return false;
  const a = parts[0]!, b = parts[1]!, c = parts[2]!;
  if (a === 0 || a === 10 || a === 127 || a >= 224) return false;
  if (a === 100 && b >= 64 && b <= 127) return false;
  if (a === 169 && b === 254) return false;
  if (a === 172 && b >= 16 && b <= 31) return false;
  if (a === 192 && (b === 168 || (b === 0 && (c === 0 || c === 2)) || (b === 88 && c === 99))) return false;
  if (a === 198 && (b === 18 || b === 19 || (b === 51 && c === 100))) return false;
  if (a === 203 && b === 0 && c === 113) return false;
  if (a === 255) return false;
  return true;
}

function ipv6Groups(address: string): number[] | null {
  const value = address.toLowerCase().split("%", 1)[0] ?? "";
  if (isIP(value) !== 6 || value.includes(".")) return null;
  const halves = value.split("::");
  if (halves.length > 2) return null;
  const left = halves[0] ? halves[0]!.split(":").filter(Boolean) : [];
  const right = halves.length === 2 && halves[1] ? halves[1]!.split(":").filter(Boolean) : [];
  if (halves.length === 1 && left.length !== 8) return null;
  const missing = halves.length === 2 ? 8 - left.length - right.length : 0;
  if (halves.length === 2 && missing < 1) return null;
  const pieces = [...left, ...Array.from({ length: missing }, () => "0"), ...right];
  if (pieces.length !== 8) return null;
  const groups = pieces.map(part => Number.parseInt(part, 16));
  if (groups.some(group => !Number.isInteger(group) || group < 0 || group > 0xffff)) return null;
  return groups;
}

export function isPublicImageAddress(address: string): boolean {
  const version = isIP(address);
  if (version === 4) return publicIpv4(address);
  if (version !== 6) return false;
  const groups = ipv6Groups(address);
  if (!groups) return false;
  const first = groups[0]!;
  const second = groups[1]!;
  if (first < 0x2000 || first > 0x3fff) return false;
  if (first === 0x2001 && (second <= 0x01ff || second === 0x0db8)) return false;
  if (first === 0x2002) return false;
  return true;
}

export async function fetchExternalImage(
  rawUrl: unknown,
  maxBytes: number,
): Promise<{ bytes: Buffer; contentType: "image/png" | "image/jpeg"; host: string }> {
  if (typeof rawUrl !== "string" || !rawUrl.trim()) throw new Error("Paste a link to a PNG or JPEG image.");
  if (rawUrl.length > 2048 || /[\s\x00-\x1f]/.test(rawUrl)) throw new Error("That link is too long or contains hidden characters.");
  let url: URL;
  try {
    url = new URL(rawUrl);
  } catch {
    throw new Error("That doesn't look like a valid link.");
  }
  if (url.protocol !== "https:") throw new Error("Only https:// links work.");
  if (url.username || url.password) throw new Error("Links with a username or password aren't allowed.");
  if (url.port && url.port !== "443") throw new Error("Only links on the normal https port (443) work.");
  const host = url.hostname.replace(/^\[|\]$/g, "").replace(/\.$/, "").toLowerCase();
  if (!host || host === "localhost" || host.endsWith(".localhost") || host.endsWith(".local")) {
    throw new Error("That link points to a private or local network address, which isn't allowed.");
  }

  let addresses: LookupAddress[];
  try {
    addresses = await dnsLookup(host, { all: true, verbatim: true });
  } catch {
    throw new Error("I couldn't find that website. Check the link.");
  }
  if (!addresses.length || addresses.some(item => !isPublicImageAddress(item.address))) {
    throw new Error("That link points to a private or local network address, which isn't allowed.");
  }

  const pinnedLookup = ((hostname: string, options: { all?: boolean }, callback: (...args: unknown[]) => void) => {
    if (hostname.replace(/\.$/, "").toLowerCase() !== host) {
      callback(new Error("Unexpected host"), undefined);
      return;
    }
    if (options?.all) callback(null, addresses);
    else callback(null, addresses[0]!.address, addresses[0]!.family);
  }) as unknown as LookupFunction;
  const agent = new https.Agent({ keepAlive: false, lookup: pinnedLookup });

  try {
    const result = await new Promise<{ bytes: Buffer; contentType: "image/png" | "image/jpeg" }>((resolveResult, reject) => {
      const request = https.request(url, {
        method: "GET",
        agent,
        timeout: 10_000,
        headers: { Accept: "image/png, image/jpeg", "User-Agent": "LemegetonCustomRoles/1.0" },
      }, incoming => {
        const status = incoming.statusCode ?? 0;
        const contentType = String(incoming.headers["content-type"] ?? "").split(";")[0]!.trim().toLowerCase();
        const lengthHeader = incoming.headers["content-length"];
        const contentLength = lengthHeader ? Number(lengthHeader) : null;
        if (status >= 300 && status < 400) {
          incoming.resume();
          reject(new Error("That link redirects somewhere else. Use the image's own address."));
          return;
        }
        if (status !== 200) {
          incoming.resume();
          reject(new Error("The website answered with an error (" + status + ")."));
          return;
        }
        if (contentType !== "image/png" && contentType !== "image/jpeg") {
          incoming.resume();
          reject(new Error("That link isn't a PNG or JPEG image."));
          return;
        }
        if (contentLength !== null && (!Number.isSafeInteger(contentLength) || contentLength > maxBytes)) {
          incoming.resume();
          reject(new Error("That image is larger than the allowed " + Math.ceil(maxBytes / (1024 * 1024)) + " MB."));
          return;
        }
        const chunks: Buffer[] = [];
        let total = 0;
        incoming.on("data", chunk => {
          const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
          total += bytes.length;
          if (total > maxBytes) {
            incoming.destroy(new Error("That image is larger than the allowed upload size."));
            return;
          }
          chunks.push(bytes);
        });
        incoming.on("end", () => resolveResult({
          bytes: Buffer.concat(chunks, total),
          contentType: contentType as "image/png" | "image/jpeg",
        }));
        incoming.on("error", reject);
      });
      request.on("timeout", () => request.destroy(new Error("That website took too long (over 10 seconds).")));
      request.on("error", reject);
      request.end();
    });
    return { ...result, host };
  } finally {
    agent.destroy();
  }
}
