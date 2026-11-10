import { createHash, randomBytes } from "node:crypto";
import type { BotConfig } from "../runtime/config.js";

const READ_LIMIT = 60;
const WRITE_LIMIT = 20;
const RATE_WINDOW_MS = 60_000;
const MAX_TRACKED = 10_000;

export interface PickerLink {
  guildId: string;
  userId: string;
  lastUsed: number;
  maxExpiresAt: number;
  idleTtlMs: number;
  reads: number[];
  writes: number[];
}

const links = new Map<string, PickerLink>();
const byMember = new Map<string, string>();

function hashToken(token: string): string {
  return createHash("sha256").update(token, "utf8").digest("hex");
}

function memberKey(guildId: string, userId: string): string {
  return guildId + ":" + userId;
}

function drop(tokenHash: string): void {
  const link = links.get(tokenHash);
  links.delete(tokenHash);
  if (link && byMember.get(memberKey(link.guildId, link.userId)) === tokenHash) {
    byMember.delete(memberKey(link.guildId, link.userId));
  }
}

function expiresAt(link: PickerLink): number {
  return Math.min(link.lastUsed + link.idleTtlMs, link.maxExpiresAt);
}

function prune(now = Date.now()): void {
  for (const [tokenHash, link] of links) {
    if (expiresAt(link) <= now) drop(tokenHash);
  }
}

export function createPickerLink(
  guildId: string,
  userId: string,
  config: BotConfig,
): { token: string; expiresAt: number; maxExpiresAt: number } {
  const now = Date.now();
  prune(now);
  revokePickerLink(guildId, userId);
  if (links.size >= MAX_TRACKED) {
    throw new Error("Too many active Custom Roles picker links. Try again after an existing link expires.");
  }
  const token = randomBytes(32).toString("base64url");
  const link: PickerLink = {
    guildId,
    userId,
    lastUsed: now,
    maxExpiresAt: now + config.customRolePickerMaxTtl * 1000,
    idleTtlMs: config.customRolePickerIdleTtl * 1000,
    reads: [],
    writes: [],
  };
  const tokenHash = hashToken(token);
  links.set(tokenHash, link);
  byMember.set(memberKey(guildId, userId), tokenHash);
  return { token, expiresAt: expiresAt(link), maxExpiresAt: link.maxExpiresAt };
}

export function lookupPickerLink(token: string): PickerLink | null {
  if (!token || token.length > 128) return null;
  const tokenHash = hashToken(token);
  const link = links.get(tokenHash);
  if (!link) return null;
  if (expiresAt(link) <= Date.now()) {
    drop(tokenHash);
    return null;
  }
  return link;
}

export function touchPickerLink(link: PickerLink): void {
  link.lastUsed = Date.now();
}

export function pickerLinkExpiry(link: PickerLink): { expires_at: number; max_expires_at: number } {
  return {
    expires_at: Math.floor(expiresAt(link) / 1000),
    max_expires_at: Math.floor(link.maxExpiresAt / 1000),
  };
}

export function allowPickerCall(link: PickerLink, write = false, now = Date.now()): boolean {
  const bucket = write ? link.writes : link.reads;
  const limit = write ? WRITE_LIMIT : READ_LIMIT;
  const cutoff = now - RATE_WINDOW_MS;
  while (bucket.length && bucket[0]! <= cutoff) bucket.shift();
  if (bucket.length >= limit) return false;
  bucket.push(now);
  return true;
}

export function revokePickerLink(guildId: string, userId: string): boolean {
  const tokenHash = byMember.get(memberKey(guildId, userId));
  if (!tokenHash) return false;
  drop(tokenHash);
  return true;
}

export function clearPickerLinks(): void {
  links.clear();
  byMember.clear();
}

export function clearPickerLinksForTests(): void {
  clearPickerLinks();
}

export function pickerTokenCountForTests(): number {
  prune();
  return links.size;
}
