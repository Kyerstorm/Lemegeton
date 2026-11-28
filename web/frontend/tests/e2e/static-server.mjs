import { createServer } from "node:http";
import { access, readFile } from "node:fs/promises";
import { extname, resolve, sep } from "node:path";

const root = resolve(process.cwd(), "out");
const port = Number(process.env.PORT || 4173);
const redirects = new Map([
  ["/index.html", "/"],
  ["/login/", "/login"],
  ["/login.html", "/login"],
  ["/login/index.html", "/login"],
  ["/custom-roles/", "/custom-roles"],
  ["/custom-roles.html", "/custom-roles"],
  ["/custom-roles/index.html", "/custom-roles"],
  ["/how-it-works/", "/how-it-works"],
  ["/how-it-works.html", "/how-it-works"],
  ["/how-it-works/index.html", "/how-it-works"],
  ["/How-it-works", "/how-it-works"],
  ["/How-it-works/", "/how-it-works"],
  ["/status/", "/status"],
  ["/status.html", "/status"],
  ["/status/index.html", "/status"],
  ["/terms-of-service/", "/terms-of-service"],
  ["/terms-of-service.html", "/terms-of-service"],
  ["/terms-of-service/index.html", "/terms-of-service"],
  ["/privacy-policy/", "/privacy-policy"],
  ["/privacy-policy.html", "/privacy-policy"],
  ["/privacy-policy/index.html", "/privacy-policy"],
  ["/community-guidelines/", "/community-guidelines"],
  ["/community-guidelines.html", "/community-guidelines"],
  ["/community-guidelines/index.html", "/community-guidelines"],
  ["/copyright-complaints/", "/copyright-complaints"],
  ["/copyright-complaints.html", "/copyright-complaints"],
  ["/copyright-complaints/index.html", "/copyright-complaints"],
  ["/dmca/", "/dmca"],
  ["/dmca.html", "/dmca"],
  ["/dmca/index.html", "/dmca"],
  ["/github/", "/github"],
  ["/issues/", "/issues"],
  ["/garden", "/"],
  ["/garden/", "/"],
  ["/garden.html", "/"],
  ["/garden/index.html", "/"],
]);
const contentTypes = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".mjs": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".xml": "application/xml; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".webm": "video/webm",
  ".gif": "image/gif",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".avif": "image/avif",
  ".ico": "image/x-icon",
};

try {
  await access(resolve(root, "index.html"));
  await access(resolve(root, "login.html"));
} catch {
  console.error("The dashboard has not been statically exported. Run npm run build before test:e2e.");
  process.exit(1);
}

createServer(async (request, response) => {
  if (request.method !== "GET" && request.method !== "HEAD") {
    response.writeHead(405).end("Method not allowed");
    return;
  }

  let url;
  try {
    url = new URL(request.url || "/", "http://localhost");
  } catch {
    response.writeHead(400).end("Invalid path");
    return;
  }

  let pathname;
  try {
    pathname = decodeURIComponent(url.pathname);
  } catch {
    response.writeHead(400).end("Invalid path");
    return;
  }

  if (pathname.split("/").some(part => part === "." || part === "..")) {
    response.writeHead(400).end("Invalid path");
    return;
  }

  const redirect = redirects.get(pathname);
  if (redirect) {
    response.writeHead(308, { Location: redirect + url.search }).end();
    return;
  }

  const segments = pathname.split("/").filter(Boolean);
  const isGuildRoute = segments.length === 2 && segments.every(segment => /^\d{17,20}$/.test(segment));
  const candidatePath = resolve(root, `.${pathname}`);
  if (candidatePath !== root && !candidatePath.startsWith(root + sep)) {
    response.writeHead(404).end("Not found");
    return;
  }

  let filePath;
  if (pathname === "/" || isGuildRoute) {
    filePath = resolve(root, "index.html");
  } else if (extname(pathname)) {
    filePath = candidatePath;
  } else {
    filePath = resolve(root, `.${pathname}.html`);
  }

  let body;
  try {
    body = await readFile(filePath);
  } catch {
    response.writeHead(404).end("Not found");
    return;
  }

  response.writeHead(200, {
    "Content-Type": contentTypes[extname(filePath)] || "application/octet-stream",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
  });
  response.end(request.method === "HEAD" ? undefined : body);
}).listen(port, "127.0.0.1", () => {
  console.log(`Static dashboard test server listening on http://127.0.0.1:${port}`);
});
