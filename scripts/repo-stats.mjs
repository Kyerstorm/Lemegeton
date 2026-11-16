#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const START_MARKER = "<!-- REPO-STATS:START -->";
const END_MARKER = "<!-- REPO-STATS:END -->";
const EXCLUDED_DIRS = new Set([
  ".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache", ".mypy_cache",
  ".ruff_cache", ".tox", "node_modules", "target", "dist", "build", ".next",
  ".netlify", "runtime-home", "logs", "data", "data_upload", "test_images", "coverage",
]);
const TEXT_SUFFIXES = new Set([
  ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".json", ".jsonc", ".md", ".mdx",
  ".rst", ".txt", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".conf", ".sh", ".bash",
  ".ps1", ".bat", ".cmd", ".rs", ".css", ".scss", ".sass", ".html", ".htm", ".sql",
  ".xml", ".svg", ".lock", ".go", ".java", ".c", ".h", ".cc", ".cpp", ".hpp",
  ".kt", ".swift", ".php", ".rb", ".lua", ".vue", ".svelte",
]);
const TEXT_NAMES = new Set([
  ".gitignore", ".dockerignore", ".env.example", "Dockerfile", "Containerfile",
  "Procfile", "Makefile", "LICENSE", "NOTICE", "COPYING", "Gemfile",
]);
const SOURCE_SUFFIXES = new Set([
  ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".rs", ".css", ".scss", ".sass",
  ".html", ".htm", ".svg", ".sql", ".sh", ".bash", ".ps1", ".bat", ".cmd",
  ".go", ".java", ".c", ".h", ".cc", ".cpp", ".hpp", ".kt", ".swift", ".php",
  ".rb", ".lua", ".vue", ".svelte",
]);
const LANGUAGE_BY_SUFFIX = {
  ".js": "JavaScript / TypeScript", ".jsx": "JavaScript / TypeScript",
  ".mjs": "JavaScript / TypeScript", ".cjs": "JavaScript / TypeScript",
  ".ts": "JavaScript / TypeScript", ".tsx": "JavaScript / TypeScript",
  ".rs": "Rust", ".css": "CSS / Sass", ".scss": "CSS / Sass",
  ".sass": "CSS / Sass", ".html": "HTML / SVG", ".htm": "HTML / SVG",
  ".svg": "HTML / SVG", ".sql": "SQL", ".sh": "Shell", ".bash": "Shell",
  ".ps1": "Shell", ".bat": "Shell", ".cmd": "Shell", ".go": "Go",
  ".java": "Java", ".c": "C", ".h": "C", ".cc": "C++", ".cpp": "C++",
  ".hpp": "C++", ".kt": "Kotlin", ".swift": "Swift", ".php": "PHP",
  ".rb": "Ruby", ".lua": "Lua", ".vue": "Vue", ".svelte": "Svelte",
};

function excluded(relativePath) {
  return relativePath.split(/[\\/]/).some((part) => EXCLUDED_DIRS.has(part));
}
function repositoryFiles() {
  const output = execFileSync("git", ["ls-files", "-z"], { cwd: ROOT });
  return output.toString("utf8").split("\0").filter(Boolean)
    .filter((relative) => !excluded(relative))
    .map((relative) => ({ relative, absolute: path.join(ROOT, relative) }));
}
function textCandidate(relative) {
  const name = path.basename(relative);
  return TEXT_NAMES.has(name) || TEXT_SUFFIXES.has(path.extname(name).toLowerCase());
}
async function collectRepositoryStats(readmeContent = null) {
  const files = repositoryFiles();
  const stats = {
    tracked_files: files.length, text_files: 0, text_lines: 0, text_characters: 0,
    text_bytes: 0, source_files: 0, source_lines: 0, nonblank_source_lines: 0,
    language_lines: {},
  };
  for (const file of files) {
    if (!textCandidate(file.relative)) continue;
    let content;
    try {
      content = readmeContent !== null && file.relative === "README.md"
        ? readmeContent : await readFile(file.absolute, "utf8");
    } catch { continue; }
    if (content.includes("\0")) continue;
    stats.text_files += 1;
    const lines = content.length === 0 ? [] : content.split(/\r?\n/);
    if (content.endsWith("\n")) lines.pop();
    stats.text_lines += lines.length;
    stats.text_characters += content.replace(/[\r\n]/g, "").length;
    try { stats.text_bytes += (await stat(file.absolute)).size; }
    catch { stats.text_bytes += Buffer.byteLength(content, "utf8"); }
    const suffix = path.extname(file.relative).toLowerCase();
    if (!SOURCE_SUFFIXES.has(suffix)) continue;
    stats.source_files += 1;
    stats.source_lines += lines.length;
    stats.nonblank_source_lines += lines.filter((line) => line.trim().length > 0).length;
    const language = LANGUAGE_BY_SUFFIX[suffix] ?? "Other";
    stats.language_lines[language] = (stats.language_lines[language] ?? 0) + lines.length;
  }
  return stats;
}
function formatBytes(size) {
  let value = Number(size);
  for (const unit of ["B", "KB", "MB", "GB", "TB"]) {
    if (value < 1024 || unit === "TB") return unit === "B" ? `${Math.round(value).toLocaleString()} B` : `${value.toFixed(1)} ${unit}`;
    value /= 1024;
  }
  return `${value.toFixed(1)} TB`;
}
function renderReadmeTable(stats, refreshedAt) {
  const languageBreakdown = Object.entries(stats.language_lines)
    .sort(([aName, aCount], [bName, bCount]) => bCount - aCount || aName.localeCompare(bName))
    .map(([name, count]) => `${name}: ${count.toLocaleString()} lines`).join("; ") || "No source files detected";
  return [
    "| Metric | Current total |",
    "|:--|--:|",
    `| Tracked files | ${stats.tracked_files.toLocaleString()} |`,
    `| Text files scanned | ${stats.text_files.toLocaleString()} |`,
    `| Source code files | ${stats.source_files.toLocaleString()} |`,
    `| Source lines (including blank lines) | ${stats.source_lines.toLocaleString()} |`,
    `| Non-blank source lines | ${stats.nonblank_source_lines.toLocaleString()} |`,
    `| Text lines (code, docs, and configuration) | ${stats.text_lines.toLocaleString()} |`,
    `| Characters (excluding line breaks) | ${stats.text_characters.toLocaleString()} |`,
    `| Text file size | ${formatBytes(stats.text_bytes)} |`,
    `| Source line breakdown | ${languageBreakdown} |`,
    `| Last refreshed (UTC) | ${refreshedAt} |`,
  ].join("\n");
}
async function updateReadme() {
  const readmePath = path.join(ROOT, "README.md");
  const current = await readFile(readmePath, "utf8");
  if (current.split(START_MARKER).length !== 2 || current.split(END_MARKER).length !== 2) {
    throw new Error(`README.md must contain exactly one ${START_MARKER} and ${END_MARKER} marker.`);
  }
  const refreshedAt = new Date().toISOString().slice(0, 16).replace("T", " ") + " UTC";
  let updated = current;
  for (let index = 0; index < 10; index += 1) {
    const stats = await collectRepositoryStats(updated);
    const table = renderReadmeTable(stats, refreshedAt);
    const start = updated.indexOf(START_MARKER) + START_MARKER.length;
    const end = updated.indexOf(END_MARKER, start);
    const next = updated.slice(0, start) + "\n" + table + "\n" + updated.slice(end);
    if (next === updated) break;
    updated = next;
  }
  if (updated !== current) {
    await writeFile(readmePath, updated, "utf8");
    return true;
  }
  return false;
}
const shouldUpdate = process.argv.includes("--update-readme");
if (shouldUpdate) {
  const changed = await updateReadme();
  process.stdout.write(changed ? "README statistics refreshed.\n" : "README statistics already current.\n");
}
const stats = await collectRepositoryStats();
process.stdout.write(`Tracked files: ${stats.tracked_files.toLocaleString()}\n`);
process.stdout.write(`Source files: ${stats.source_files.toLocaleString()}\n`);
process.stdout.write(`Source lines: ${stats.source_lines.toLocaleString()} (${stats.nonblank_source_lines.toLocaleString()} non-blank)\n`);
process.stdout.write(`Text characters (excluding line breaks): ${stats.text_characters.toLocaleString()}\n`);
process.stdout.write(`Text size: ${formatBytes(stats.text_bytes)}\n`);
