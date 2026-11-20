import sharp from "sharp";
import { safeAtlasImageUrl, type AtlasGraphPath, type AtlasGraphResult, type AtlasRelation, type MediaCategory } from "../integration/atlas.js";

const WIDTH = 1450;
const HEIGHT = 950;
const CENTER_X = WIDTH / 2;
const CENTER_Y = 530;
const MAX_NODES = 8;
const CARD_WIDTH = 204;
const CARD_HEIGHT = 136;

function escapeXml(value: string): string {
  const entities: Record<string, string> = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&apos;",
  };
  return value.replace(/[&<>"']/g, character => entities[character] ?? character);
}

function shorten(value: string, max: number): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (normalized.length <= max) return normalized;
  return normalized.slice(0, Math.max(1, max - 1)).trimEnd() + "…";
}

function provenanceColor(kind: AtlasRelation["sourceKind"]): string {
  if (kind === "community") return "#f5f5f5";
  if (kind === "recommendation") return "#8e8e8e";
  return "#606060";
}

function provenanceDash(kind: AtlasRelation["sourceKind"]): string {
  return kind === "recommendation" ? 'stroke-dasharray="8 7"' : "";
}

function text(x: number, y: number, content: string, size: number, color: string, weight = 400, anchor = "start"): string {
  return `<text x="${x}" y="${y}" text-anchor="${anchor}" fill="${color}" font-family="Arial, sans-serif" font-size="${size}" font-weight="${weight}">${escapeXml(content)}</text>`;
}

async function atlasImageData(value: string | null | undefined): Promise<string | null> {
  const url = safeAtlasImageUrl(value);
  if (!url) return null;
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(4_000), redirect: "error" });
    if (!response.ok || !response.body) return null;
    const type = response.headers.get("content-type")?.split(";")[0]?.trim().toLowerCase();
    if (!type || !["image/jpeg", "image/png", "image/webp", "image/avif"].includes(type)) return null;
    const declaredSize = Number(response.headers.get("content-length") ?? 0);
    if (declaredSize > 1_200_000) return null;
    const reader = response.body.getReader();
    const chunks: Buffer[] = [];
    let total = 0;
    try {
      while (true) {
        const part = await reader.read();
        if (part.done) break;
        total += part.value.byteLength;
        if (total > 1_200_000) {
          await reader.cancel();
          return null;
        }
        chunks.push(Buffer.from(part.value));
      }
    } finally {
      reader.releaseLock();
    }
    if (!total) return null;
    const thumbnail = await sharp(Buffer.concat(chunks, total), { limitInputPixels: 12_000_000 })
      .resize(160, 112, { fit: "cover", withoutEnlargement: true })
      .jpeg({ quality: 72, mozjpeg: true })
      .toBuffer();
    return "data:image/jpeg;base64," + thumbnail.toString("base64");
  } catch {
    return null;
  }
}


export async function renderAtlasGraphSvgSnapshot(
  title: string,
  category: MediaCategory | string,
  graph: AtlasGraphResult,
  path: AtlasGraphPath | null = null,
): Promise<Buffer> {
  const width = 1800;
  const height = 1480;
  const centerX = width / 2;
  const centerY = 760;
  const cardWidth = 184;
  const cardHeight = 132;
  const root = graph.nodes.find(node => node.id === graph.rootId);
  if (!root) {
    const fallback = '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="400" viewBox="0 0 1200 400">' +
      '<rect width="100%" height="100%" fill="#080808"/>' +
      text(48, 100, "LEMEGETON / KNOWLEDGE ATLAS", 14, "#999999", 600) +
      text(48, 190, shorten(title, 60), 36, "#ffffff", 700) +
      text(48, 232, category.replace(/_/g, " ").toUpperCase() + " · NO ROOT NODE", 13, "#999999", 500) +
      '</svg>';
    return Buffer.from(fallback);
  }
  const imageNodes = graph.nodes.slice(0, 25);
  const imageEntries = await Promise.all(imageNodes.map(async node =>
    [node.id, await atlasImageData(node.imageUrl)] as const,
  ));
  const images = new Map(imageEntries);

  const positions = new Map<string, { x: number; y: number }>();
  positions.set(root.id, { x: centerX, y: centerY });
  for (let depth = 1; depth <= 3; depth += 1) {
    const nodes = graph.nodes
      .filter(node => node.id !== graph.rootId && node.depth === depth)
      .sort((left, right) => left.title.localeCompare(right.title));
    const radius = depth === 1 ? 285 : depth === 2 ? 440 : 560;
    const step = (Math.PI * 2) / Math.max(nodes.length, 1);
    nodes.forEach((node, index) => {
      const angle = -Math.PI / 2 + index * step + (depth === 2 ? step / 2 : 0);
      positions.set(node.id, {
        x: centerX + Math.cos(angle) * radius,
        y: centerY + Math.sin(angle) * radius,
      });
    });
  }

  const pathEdgeKeys = new Set((path?.edges ?? []).map(edge =>
    [edge.from, edge.to, edge.relationType, edge.sourceKind].join("|"),
  ));
  const edges = graph.edges.map(edge => {
    const from = positions.get(edge.from);
    const to = positions.get(edge.to);
    if (!from || !to) return "";
    const highlighted = pathEdgeKeys.has([edge.from, edge.to, edge.relationType, edge.sourceKind].join("|"));
    const color = provenanceColor(edge.sourceKind);
    return [
      '<line x1="' + from.x.toFixed(1) + '" y1="' + from.y.toFixed(1) +
      '" x2="' + to.x.toFixed(1) + '" y2="' + to.y.toFixed(1) +
      '" stroke="' + (highlighted ? "#ffffff" : color) +
      '" stroke-width="' + (highlighted ? "6" : "2") +
      '" opacity="' + (highlighted ? "1" : ".62") + '" ' +
      provenanceDash(edge.sourceKind) + ' />',
    ].join("");
  }).join("");

  const cards = graph.nodes
    .filter(node => node.id !== graph.rootId)
    .slice(0, 40)
    .map(node => {
      const point = positions.get(node.id);
      if (!point) return "";
      const incoming = graph.edges.find(edge => edge.to === node.id);
      const kind = node.sourceKind ?? incoming?.sourceKind ?? "provider";
      const relationType = node.relationType ?? incoming?.relationType ?? "related";
      const sourceLabel = node.sourceLabel ?? incoming?.sourceLabel ?? kind;
      const color = provenanceColor(kind);
      const left = point.x - cardWidth / 2;
      const top = point.y - cardHeight / 2;
      return [
        "<g>",
        '<rect x="' + left.toFixed(1) + '" y="' + top.toFixed(1) + '" width="' + cardWidth +
          '" height="' + cardHeight + '" rx="13" fill="#111111" stroke="' + color + '" stroke-width="2" />',
        '<rect x="' + (left + 13) + '" y="' + (top + 12) + '" width="4" height="' + (cardHeight - 24) +
          '" rx="2" fill="' + color + '" />',
        ...(images.get(node.id) ? [
          '<image href="' + images.get(node.id) + '" x="' + (left + 12) + '" y="' + (top + 18) + '" width="48" height="66" preserveAspectRatio="xMidYMid slice" />',
        ] : []),
        text(left + (images.get(node.id) ? 72 : 27), top + 30, shorten(node.category.replace(/_/g, " ").toUpperCase(), 18), 9, "#999999", 600),
        text(left + (images.get(node.id) ? 72 : 27), top + 55, shorten(node.title, images.get(node.id) ? 12 : 22), 14, "#f3f3f3", 700),
        text(left + (images.get(node.id) ? 72 : 27), top + 79, shorten(relationType, images.get(node.id) ? 14 : 22), 10, "#c0c0c0", 500),
        text(left + 27, top + 102, kind.toUpperCase() + " · " + shorten(sourceLabel, 16), 8, color, 600),
        text(left + 27, top + 118, shorten((node.provider ? node.provider + ":" + (node.providerId ?? "") + " · " : "") + (incoming?.evidence ?? "No additional evidence"), 32), 7, "#a0a0a0", 400),
        "</g>",
      ].join("");
    }).join("");

  const rootCard = [
    '<rect x="' + (centerX - 150) + '" y="' + (centerY - 80) +
      '" width="300" height="160" rx="24" fill="#080808" stroke="#f3f3f3" stroke-width="3" />',
    '<rect x="' + (centerX - 137) + '" y="' + (centerY - 67) +
      '" width="274" height="134" rx="16" fill="none" stroke="#484848" stroke-width="1" />',
    ...(images.get(root.id) ? [
      '<image href="' + images.get(root.id) + '" x="' + (centerX - 38) + '" y="' + (centerY - 66) + '" width="76" height="58" preserveAspectRatio="xMidYMid slice" />',
    ] : []),
    text(centerX, centerY + (images.get(root.id) ? 16 : -23), root.category.replace(/_/g, " ").toUpperCase(), 11, "#aaaaaa", 600, "middle"),
    text(centerX, centerY + (images.get(root.id) ? 42 : 14), shorten(root.title, 27), 22, "#ffffff", 700, "middle"),
    text(centerX, centerY + (images.get(root.id) ? 64 : 45), "ROOT NODE", 9, "#888888", 600, "middle"),
  ].join("");

  const footer = graph.nodes.length + " nodes · " + graph.edges.length + " connections" +
    (graph.truncated ? " · graph truncated at configured limit" : "") +
    (path ? " · " + path.edges.length + "-step path highlighted" : "");
  const svg = [
    '<svg xmlns="http://www.w3.org/2000/svg" width="' + width + '" height="' + height + '" viewBox="0 0 ' + width + " " + height + '">',
    '<defs><radialGradient id="background" cx="50%" cy="48%" r="75%"><stop offset="0%" stop-color="#1b1b1b"/><stop offset="100%" stop-color="#050505"/></radialGradient></defs>',
    '<rect width="100%" height="100%" fill="url(#background)"/>',
    '<path d="M0 90 H' + width + '" stroke="#303030"/>',
    text(58, 48, "LEMEGETON / KNOWLEDGE ATLAS", 12, "#a5a5a5", 600),
    text(58, 145, shorten(title, 62), 38, "#f4f4f4", 700),
    text(58, 178, category.replace(/_/g, " ").toUpperCase() + " · MULTI-HOP RELATIONSHIP GRAPH", 12, "#999999", 500),
    edges,
    rootCard,
    cards,
    '<path d="M58 ' + (height - 70) + " H" + (width - 58) + '" stroke="#303030"/>',
    text(58, height - 38, footer, 11, "#999999", 500),
    text(width - 58, height - 38, "PROVIDER · RECOMMENDATION · COMMUNITY", 10, "#777777", 500, "end"),
    "</svg>",
  ].join("");
  return Buffer.from(svg);
}

export async function renderAtlasGraphSnapshot(
  title: string,
  category: MediaCategory | string,
  graph: AtlasGraphResult,
  path: AtlasGraphPath | null = null,
): Promise<Buffer> {
  const svg = await renderAtlasGraphSvgSnapshot(title, category, graph, path);
  return sharp(svg).png().toBuffer();
}

export async function renderAtlasSnapshot(
  title: string,
  category: MediaCategory | string,
  relationships: AtlasRelation[],
): Promise<Buffer> {
  const selected = relationships.slice(0, MAX_NODES);
  const nodes = selected.map((relation, index) => {
    const angle = (index / Math.max(selected.length, 1)) * Math.PI * 2 - Math.PI / 2;
    return {
      relation,
      x: CENTER_X + Math.cos(angle) * 280,
      y: CENTER_Y + Math.sin(angle) * 280,
    };
  });

  const edges = nodes.map(({ relation, x, y }) =>
    `<line x1="${CENTER_X}" y1="${CENTER_Y}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="${provenanceColor(relation.sourceKind)}" stroke-width="2" opacity=".7" ${provenanceDash(relation.sourceKind)} />`
  ).join("");

  const cards = nodes.map(({ relation, x, y }) => {
    const left = x - CARD_WIDTH / 2;
    const top = y - CARD_HEIGHT / 2;
    const color = provenanceColor(relation.sourceKind);
    const kind = relation.sourceKind.toUpperCase();
    return [
      "<g>",
      `<rect x="${left}" y="${top}" width="${CARD_WIDTH}" height="${CARD_HEIGHT}" rx="15" fill="#111111" stroke="${color}" stroke-width="2" />`,
      `<rect x="${left+15}" y="${top+13}" width="4" height="${CARD_HEIGHT-26}" rx="2" fill="${color}" />`,
      text(left + 30, top + 31, shorten(relation.category.replace(/_/g, " "), 23).toUpperCase(), 11, "#9a9a9a", 600),
      text(left + 30, top + 59, shorten(relation.title, 27), 17, "#f2f2f2", 700),
      text(left + 30, top + 84, shorten(relation.relationType, 25), 12, "#c0c0c0", 500),
      text(left + 30, top + 112, `${kind} · ${shorten(relation.source, 19)}`, 10, color, 600),
      "</g>",
    ].join("");
  }).join("");

  const footer = selected.length < relationships.length
    ? `${selected.length} of ${relationships.length} direct connections shown`
    : `${relationships.length} direct connection${relationships.length === 1 ? "" : "s"}`;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${WIDTH}" height="${HEIGHT}" viewBox="0 0 ${WIDTH} ${HEIGHT}">
    <defs>
      <radialGradient id="background" cx="50%" cy="48%" r="75%">
        <stop offset="0%" stop-color="#1b1b1b"/>
        <stop offset="100%" stop-color="#050505"/>
      </radialGradient>
    </defs>
    <rect width="100%" height="100%" fill="url(#background)"/>
    <path d="M0 80 H${WIDTH}" stroke="#303030"/>
    ${text(58, 48, "LEMEGETON / KNOWLEDGE ATLAS", 12, "#a5a5a5", 600)}
    ${text(58, 122, shorten(title, 56), 34, "#f4f4f4", 700)}
    ${text(58, 151, `${category.replace(/_/g, " ")} · DIRECT RELATIONSHIPS`.toUpperCase(), 12, "#999999", 500)}
    ${edges}
    <circle cx="${CENTER_X}" cy="${CENTER_Y}" r="113" fill="#080808" stroke="#ededed" stroke-width="3"/>
    <circle cx="${CENTER_X}" cy="${CENTER_Y}" r="101" fill="none" stroke="#454545" stroke-width="1"/>
    ${text(CENTER_X, CENTER_Y-17, category.replace(/_/g, " ").toUpperCase(), 12, "#aaa", 600, "middle")}
    ${text(CENTER_X, CENTER_Y+18, shorten(title, 24), 22, "#fff", 700, "middle")}
    ${cards}
    <path d="M58 ${HEIGHT-63} H${WIDTH-58}" stroke="#303030"/>
    ${text(58, HEIGHT-34, footer, 11, "#999999", 500)}
    ${text(WIDTH-58, HEIGHT-34, "PROVIDER · RECOMMENDATION · COMMUNITY", 10, "#777777", 500, "end")}
  </svg>`;
  return sharp(Buffer.from(svg)).png().toBuffer();
}
