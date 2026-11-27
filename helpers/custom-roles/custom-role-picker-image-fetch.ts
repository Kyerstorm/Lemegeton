import { lookup as dnsLookup } from "node:dns/promises";
import type { LookupAddress } from "node:dns";
import { isPublicUnicastAddress } from "../security/public-address.js";
export { isPublicUnicastAddress as isPublicImageAddress } from "../security/public-address.js";
import https from "node:https";

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
  if (!addresses.length || addresses.some(item => !isPublicUnicastAddress(item.address))) {
    throw new Error("That link points to a private or local network address, which isn't allowed.");
  }

  const agent = new https.Agent({
    keepAlive: false,
    lookup: (hostname, options, callback) => {
      if (hostname.replace(/\.$/, "").toLowerCase() !== host) {
        if (options.all) callback(new Error("Unexpected host"), []);
        else callback(new Error("Unexpected host"), "", 0);
        return;
      }
      const candidates = addresses.filter(address => !options.family || options.family === 0 || address.family === options.family);
      if (!candidates.length) {
        if (options.all) callback(new Error("No validated address matches the requested family"), []);
        else callback(new Error("No validated address matches the requested family"), "", 0);
        return;
      }
      if (options.all) callback(null, candidates);
      else callback(null, candidates[0]!.address, candidates[0]!.family);
    },
  });

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
      const deadline = setTimeout(() => request.destroy(new Error("That website took too long (over 10 seconds).")), 10_000);
      deadline.unref?.();
      request.on("close", () => clearTimeout(deadline));
      request.on("timeout", () => request.destroy(new Error("That website stopped responding.")));
      request.on("error", reject);
      request.end();
    });
    return { ...result, host };
  } finally {
    agent.destroy();
  }
}
