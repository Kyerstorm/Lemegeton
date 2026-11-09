import sharp from "sharp";
import type { AtlasRelation, MediaCategory } from "../providers/atlas.js";

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
