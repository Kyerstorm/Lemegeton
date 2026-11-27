"use strict";

import { lstat, readFile, realpath } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

export const DEFAULT_LIMITS = Object.freeze({
  maxClaims: 160,
  maxSourceFiles: 96,
  maxFileBytes: 512 * 1024,
  maxTotalBytes: 8 * 1024 * 1024,
});

const isWithin = (root, target) => target === root || target.startsWith(root + path.sep);

function safeRelativePath(value) {
  if (typeof value !== "string" || value.length === 0 || value.length > 240) return false;
  if (value.includes("\\") || value.startsWith("/") || /^[a-z]:/i.test(value)) return false;

  const parts = value.split("/");
  if (parts.some(part => !part || part === "." || part === "..")) return false;
  if (path.posix.normalize(value) !== value) return false;

  const blocked = new Set([".git", "node_modules", "target", "dist", "data", "storage", "backups", "logs"]);
  if (parts.some(part => blocked.has(part.toLowerCase()))) return false;

  const filename = parts.at(-1).toLowerCase();
  if (filename === ".env" || (filename.startsWith(".env.") && filename !== ".env.example")) return false;
  if (/\.(pem|key|p12|pfx|db|sqlite|sqlite3|log)$/i.test(filename)) return false;

  return true;
}

function containsSymbol(source, symbol) {
  const escaped = Array.from(symbol, character =>
    ".\\^$*+?()[]{}|".includes(character) ? "\\" + character : character
  ).join("");
  return new RegExp("(^|[^\\w$])" + escaped + "(?=$|[^\\w$])", "m").test(source);
}

export async function validateReport(report, options = {}) {
  const limits = { ...DEFAULT_LIMITS, ...options.limits };
  const errors = [];
  const verifiedClaims = [];
  const cache = new Map();
  const seenClaims = new Set();
  let totalBytes = 0;

  const addError = (claimIndex, reason) => errors.push({ claimIndex, reason });

  if (!report || typeof report !== "object" || Array.isArray(report)) {
    return { valid: false, errors: [{ claimIndex: null, reason: "Report must be a JSON object." }], verifiedClaims };
  }
  if (report.schemaVersion !== 1) addError(null, "Unsupported or missing schemaVersion; expected 1.");
  if (!Array.isArray(report.claims)) addError(null, "Report claims must be an array.");

  if (errors.length || !Array.isArray(report.claims)) {
    return { valid: false, errors, verifiedClaims };
  }
  if (report.claims.length === 0) {
    addError(null, "Report must include at least one evidence claim.");
    return { valid: false, errors, verifiedClaims };
  }
  if (report.claims.length > limits.maxClaims) {
    addError(null, "Claim count exceeds the configured limit.");
    return { valid: false, errors, verifiedClaims };
  }

  let root;
  try {
    root = await realpath(options.root ?? process.cwd());
  } catch {
    return { valid: false, errors: [{ claimIndex: null, reason: "Evidence root cannot be accessed." }], verifiedClaims };
  }

  for (let index = 0; index < report.claims.length; index += 1) {
    const claim = report.claims[index];

    if (!claim || typeof claim !== "object" || Array.isArray(claim)) {
      addError(index, "Claim must be an object.");
      continue;
    }
    const { path: relativePath, symbol, evidence } = claim;

    if (!safeRelativePath(relativePath)) {
      addError(index, "Evidence path is invalid or points to a protected/generated location.");
      continue;
    }
    if (typeof symbol !== "string" || !/^[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*$/.test(symbol) || symbol.length > 200) {
      addError(index, "Claim must identify a concrete source symbol.");
      continue;
    }
    if (typeof evidence !== "string" || evidence.length < 8 || evidence.length > 1000) {
      addError(index, "Evidence must be an exact source excerpt between 8 and 1000 characters.");
      continue;
    }

    const key = relativePath + "\u0000" + symbol + "\u0000" + evidence;
    if (seenClaims.has(key)) {
      addError(index, "Duplicate evidence claim.");
      continue;
    }
    seenClaims.add(key);

    let sourceEntry = cache.get(relativePath);
    if (!sourceEntry) {
      const absolutePath = path.resolve(root, ...relativePath.split("/"));
      if (!isWithin(root, absolutePath)) {
        addError(index, "Evidence path escapes the selected source root.");
        continue;
      }

      try {
        let cursor = root;
        let linked = false;
        for (const part of relativePath.split("/")) {
          cursor = path.join(cursor, part);
          const current = await lstat(cursor);
          if (current.isSymbolicLink()) {
            linked = true;
            break;
          }
        }
        if (linked) {
          addError(index, "Symbolic-link evidence paths are not accepted.");
          continue;
        }

        const resolvedPath = await realpath(absolutePath);
        if (!isWithin(root, resolvedPath)) {
          addError(index, "Resolved evidence path escapes the selected source root.");
          continue;
        }

        const metadata = await lstat(resolvedPath);
        if (!metadata.isFile()) {
          addError(index, "Evidence path must point to a regular file.");
          continue;
        }
        if (metadata.size > limits.maxFileBytes) {
          addError(index, "Source file exceeds the per-file byte limit.");
          continue;
        }
        if (cache.size >= limits.maxSourceFiles) {
          addError(index, "Source file count exceeds the configured limit.");
          continue;
        }
        if (totalBytes + metadata.size > limits.maxTotalBytes) {
          addError(index, "Evidence reads exceed the total byte limit.");
          continue;
        }

        const source = await readFile(resolvedPath, "utf8");
        if (source.includes("\u0000")) {
          addError(index, "Binary-like source files are not accepted.");
          continue;
        }

        totalBytes += metadata.size;
        sourceEntry = { source, bytes: metadata.size };
        cache.set(relativePath, sourceEntry);
      } catch {
        addError(index, "Evidence source is missing or cannot be read.");
        continue;
      }
    }

    if (!containsSymbol(sourceEntry.source, symbol)) {
      addError(index, "Claimed symbol does not exist in the cited source file.");
      continue;
    }

    const excerptIndex = sourceEntry.source.indexOf(evidence);
    if (excerptIndex < 0) {
      addError(index, "Exact evidence excerpt does not exist in the cited source file.");
      continue;
    }

    verifiedClaims.push({
      path: relativePath,
      symbol,
      line: sourceEntry.source.slice(0, excerptIndex).split("\n").length,
      bytesRead: sourceEntry.bytes,
    });
  }

  return {
    valid: errors.length === 0 && verifiedClaims.length === report.claims.length,
    errors,
    verifiedClaims,
    limits,
    totalBytesRead: totalBytes,
  };
}

async function main(argv) {
  const args = new Map();
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    if (key === "--help" || key === "-h") {
      process.stdout.write("Usage: node scripts/ai-reverse-engineering-guard.mjs --report <report.json> [--root <source-root>]\n");
      return;
    }
    if (!key.startsWith("--") || !argv[index + 1] || argv[index + 1].startsWith("--")) {
      throw new Error("Expected --report <file> and optional --root <directory>.");
    }
    args.set(key, argv[++index]);
  }

  const reportPath = args.get("--report");
  if (!reportPath) throw new Error("Missing required --report <file> argument.");

  const report = JSON.parse(await readFile(path.resolve(reportPath), "utf8"));
  const result = await validateReport(report, { root: path.resolve(args.get("--root") ?? process.cwd()) });
  process.stdout.write(JSON.stringify(result, null, 2) + "\n");
  if (!result.valid) process.exitCode = 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main(process.argv.slice(2)).catch(error => {
    process.stderr.write((error instanceof Error ? error.message : "Validation failed.") + "\n");
    process.exitCode = 2;
  });
}
