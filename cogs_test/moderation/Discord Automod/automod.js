/**
 * automod.js
 *
 * Full features:
 *  - Better-sqlite3 backed storage (guild config, infractions, caches)
 *  - Perspective API (text moderation) with retries + backoff
 *  - Google Vision SafeSearch with caching and retries
 *  - Full Discord native AutoMod sync (create/update/delete), with schema translation
 *  - Dashboard hub command (/automod dashboard) with selects, modals, and buttons
 *  - Modal submit handling for adding/editing triggers and config values
 *  - Per-guild spam counters with adaptive escalation: warn -> temp_mute -> kick -> ban
 *  - Message pipeline integrating text checks, image checks, triggers, spam checks
 *  - Elegant Neo-dark embed styling + moderator log embeds with interactive buttons
 *  - Microservice mode: stdin/stdout JSON-RPC interface for Python integration
 *  - Fully verbose comments and internal documentation
 *
 * Environment variables:
 *  - BOT_TOKEN            Optional if you want this process to run as the bot
 *  - PERSPECTIVE_KEY      Optional (text moderation)
 *  - GOOGLE_VISION_KEY    Optional (image moderation)
 *  - SQLITE_DB_PATH       Optional DB path (defaults to ./automod_neo.db)
 *  - OWNER_ID             Optional: bot owner id for debug/admin features
 *
 * Notes on native Discord AutoMod:
 *  - Creating / editing Discord AutoMod rule entities requires the application.commands and proper scope/permissions.
 *  - This module implements full REST-based create/update/delete flows using the application's bot token.
 *  - Sync operations are guarded (preview -> confirm) via the dashboard to avoid accidentally overwriting rules.
 *
 * Big file — be patient while reading. It's intentionally verbose for maintainability.
 */

/* eslint-disable no-console */

// ----------------------------- IMPORTS & GLOBAL CONSTS -----------------------------
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const fetch = require('node-fetch'); // safe cross-node compatibility
const Database = require('better-sqlite3');
const { REST } = require('@discordjs/rest');
const { Routes } = require('discord-api-types/v10');
const { SlashCommandBuilder, ModalBuilder, TextInputBuilder, TextInputStyle, ActionRowBuilder: ARBuilder } = require('@discordjs/builders');

const {
  Client,
  GatewayIntentBits,
  Partials,
  EmbedBuilder,
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  PermissionsBitField,
  StringSelectMenuBuilder,
  ModalSubmitInteraction,
  TextInputBuilder: DJTextInputBuilder,
  TextInputStyle: DJTextInputStyle,
  ChannelType
} = require('discord.js');

// Environment / runtime config
const BOT_TOKEN = process.env.BOT_TOKEN || null;
const PERSPECTIVE_KEY = process.env.PERSPECTIVE_KEY || null;
const GOOGLE_VISION_KEY = process.env.GOOGLE_VISION_KEY || null;
const DB_PATH = process.env.SQLITE_DB_PATH || path.join(process.cwd(), 'automod_neo.db');
const OWNER_ID = process.env.OWNER_ID || null;

// Neo-dark aesthetic constants
const COLORS = {
  background: 0x0d1117,
  accent: 0x00e6ff,
  success: 0x50fa7b,
  warning: 0xffb86b,
  danger: 0xff4d8f,
  info: 0x8be9fd,
  text: 0xc9d1d9,
};

// Small helper emojis for UI
const EMOJI = {
  check: '✅',
  warn: '⚠️',
  error: '❌',
  sync: '🔁',
  spark: '✨',
  brain: '🧠',
  shield: '🛡️',
  logs: '📜',
};

// Vision cache TTL (24 hours)
const VISION_CACHE_TTL_MS = 24 * 60 * 60 * 1000;

// ----------------------------- DB LAYER (better-sqlite3) -----------------------------
/**
 * We use better-sqlite3 for synchronous, safe, and fast DB operations.
 * The DB will contain:
 *  - guilds: guild_id (PK), config_json (TEXT)
 *  - infractions: id, guild_id, user_id, moderator_id, action, reason, meta_json, created_at
 *  - vision_cache: sha1 (PK), response_json, created_at (ms)
 *  - spam_counters: guild_id, user_id, timestamps_json (rolling window)
 *
 * We provide helpers to get/set guild configs, add infractions, manage vision cache,
 * and manage spam counters efficiently.
 */

let db = null;
function initDb() {
  if (db) return;
  try {
    db = new Database(DB_PATH);
    // enable WAL for concurrency and performance
    db.pragma('journal_mode = WAL');
    // create tables
    db.exec(`
      CREATE TABLE IF NOT EXISTS guilds (
        guild_id TEXT PRIMARY KEY,
        config_json TEXT NOT NULL
      );
    `);
    db.exec(`
      CREATE TABLE IF NOT EXISTS infractions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT,
        user_id TEXT,
        moderator_id TEXT,
        action TEXT,
        reason TEXT,
        meta_json TEXT,
        created_at TEXT DEFAULT (datetime('now'))
      );
    `);
    db.exec(`
      CREATE TABLE IF NOT EXISTS vision_cache (
        sha1 TEXT PRIMARY KEY,
        response_json TEXT,
        created_at INTEGER
      );
    `);
    db.exec(`
      CREATE TABLE IF NOT EXISTS spam_counters (
        guild_id TEXT,
        user_id TEXT,
        timestamps_json TEXT,
        PRIMARY KEY (guild_id, user_id)
      );
    `);
    // index for infractions search
    db.exec(`CREATE INDEX IF NOT EXISTS infractions_guild_idx ON infractions (guild_id);`);
  } catch (e) {
    console.error('Failed to initialize DB:', e);
    process.exit(1);
  }
}
initDb();

// Default guild configuration — we maintain a robust shape and versioning key if needed in future
const DEFAULT_GUILD_CFG = {
  version: 1,
  logChannelId: null,
  modRoleIds: [],
  trustedRoleIds: [],
  bannedWords: [],
  automodTriggers: [], // fallback triggers stored as objects
  spamThreshold: { messages: 5, seconds: 8, escalations: [ {count:3, action: 'temp_mute:60'}, {count:6, action: 'temp_mute:3600'} ]},
  linksWhitelist: [],
  linksBlacklist: [],
  nsfwScanEnabled: true,
  muteRoleId: null,
  tempMutes: [], // persisted mutes for fallback
  perspectiveThresholds: {
    TOXICITY: { threshold: 0.85, action: 'delete+warn' },
    INSULT: { threshold: 0.85, action: 'delete+warn' },
    SEVERE_TOXICITY: { threshold: 0.85, action: 'delete+warn' },
    IDENTITY_ATTACK: { threshold: 0.85, action: 'delete+warn' },
    THREAT: { threshold: 0.80, action: 'delete+warn' },
    SEXUALLY_EXPLICIT: { threshold: 0.80, action: 'delete+warn' }
  },
  visionThresholds: {
    adult: { levels: ['LIKELY','VERY_LIKELY'], action: 'delete+warn' },
    violence: { levels: ['LIKELY','VERY_LIKELY'], action: 'delete+warn' },
    racy: { levels: ['LIKELY','VERY_LIKELY'], action: 'delete+warn' }
  },
  automodSync: true, // sync fallback rules to native AutoMod by default (opt-in per server)
};

// DB helpers
function _getConfigRow(guildId) {
  const row = db.prepare('SELECT config_json FROM guilds WHERE guild_id = ?').get(guildId);
  if (!row) {
    const cfg = JSON.parse(JSON.stringify(DEFAULT_GUILD_CFG));
    db.prepare('INSERT OR REPLACE INTO guilds (guild_id, config_json) VALUES (?, ?)').run(guildId, JSON.stringify(cfg));
    return cfg;
  }
  try { return JSON.parse(row.config_json); } catch (e) { return JSON.parse(JSON.stringify(DEFAULT_GUILD_CFG)); }
}
function getGuildConfig(guildId) {
  // defensive copy
  return JSON.parse(JSON.stringify(_getConfigRow(guildId)));
}
function setGuildConfig(guildId, config) {
  db.prepare('INSERT OR REPLACE INTO guilds (guild_id, config_json) VALUES (?, ?)').run(guildId, JSON.stringify(config));
}
function addInfraction(guildId, userId, moderatorId, action, reason, meta = {}) {
  db.prepare('INSERT INTO infractions (guild_id, user_id, moderator_id, action, reason, meta_json) VALUES (?, ?, ?, ?, ?, ?)')
    .run(guildId, userId, moderatorId, action, reason, JSON.stringify(meta || {}));
}
function getRecentInfractions(guildId, limit = 50) {
  return db.prepare('SELECT id,user_id,moderator_id,action,reason,meta_json,created_at FROM infractions WHERE guild_id = ? ORDER BY id DESC LIMIT ?').all(guildId, limit)
    .map(r => ({ ...r, meta: tryParse(r.meta_json) }));
}
function tryParse(s) {
  try { return s ? JSON.parse(s) : null; } catch (e) { return null; }
}

// Vision cache helpers
function setVisionCache(sha1hash, responseObj) {
  try {
    db.prepare('INSERT OR REPLACE INTO vision_cache (sha1, response_json, created_at) VALUES (?, ?, ?)').run(sha1hash, JSON.stringify(responseObj), Date.now());
  } catch (e) {
    console.warn('setVisionCache failed', e);
  }
}
function getVisionCache(sha1hash) {
  try {
    const row = db.prepare('SELECT response_json, created_at FROM vision_cache WHERE sha1 = ?').get(sha1hash);
    if (!row) return null;
    if (Date.now() - row.created_at > VISION_CACHE_TTL_MS) {
      db.prepare('DELETE FROM vision_cache WHERE sha1 = ?').run(sha1hash);
      return null;
    }
    return tryParse(row.response_json);
  } catch (e) {
    console.warn('getVisionCache failed', e);
    return null;
  }
}

// Spam counter helpers (rolling window)
function getSpamTimestamps(guildId, userId) {
  const row = db.prepare('SELECT timestamps_json FROM spam_counters WHERE guild_id = ? AND user_id = ?').get(guildId, userId);
  if (!row) return [];
  const arr = tryParse(row.timestamps_json) || [];
  return arr;
}
function setSpamTimestamps(guildId, userId, arr) {
  db.prepare('INSERT OR REPLACE INTO spam_counters (guild_id, user_id, timestamps_json) VALUES (?, ?, ?)').run(guildId, userId, JSON.stringify(arr || []));
}
function clearSpamTimestamps(guildId, userId) {
  db.prepare('DELETE FROM spam_counters WHERE guild_id = ? AND user_id = ?').run(guildId, userId);
}

// ----------------------------- UTILITIES -----------------------------
/**
 * Exponential backoff wrapper with jitter and optional attempts / base.
 * Accepts an async function that performs the remote call and either returns or throws.
 *
 * Behavior:
 *  - Calls fn(attemptNumber)
 *  - On error, if attempts left -> waits baseMs * (2 ** attempt) + jitter and retries
 *  - If error.status === 429, multiplies backoff by 2
 */
async function withRetries(fn, opts = {}) {
  const attempts = opts.attempts || 4;
  const baseMs = opts.baseMs || 400;
  const jitter = opts.jitter || baseMs;
  let attempt = 0;
  while (attempt < attempts) {
    try {
      return await fn(attempt);
    } catch (err) {
      attempt++;
      const status = (err && err.status) || null;
      if (attempt >= attempts) {
        // final failure
        const finalErr = new Error(`Retries exhausted after ${attempts} attempts: ${err && err.message}`);
        finalErr.cause = err;
        throw finalErr;
      }
      let backoff = Math.round(baseMs * Math.pow(2, attempt) + Math.random() * jitter);
      if (status === 429) backoff *= 2; // more gentle on rate limit
      await new Promise(res => setTimeout(res, backoff));
    }
  }
}

// small helpers
function sha1Base64(input) {
  return crypto.createHash('sha1').update(input).digest('hex');
}
function nowIso() { return new Date().toISOString(); }

// safe JSON stringify helper for logs
function safeStringify(obj, n = 2) {
  try { return JSON.stringify(obj, null, n); } catch (e) { return String(obj); }
}

// embed builder for neo-dark aesthetic
function buildEmbed({ title, description, fields = [], color = COLORS.background, footer = 'AutoMod • Neo', timestamp = true }) {
  const emb = new EmbedBuilder()
    .setTitle(title || '')
    .setDescription(description || '')
    .setColor(color)
    .setFooter({ text: footer });
  if (timestamp) emb.setTimestamp(new Date());
  fields.forEach(f => {
    emb.addFields([{ name: f.name || '\u200b', value: f.value || '\u200b', inline: !!f.inline }]);
  });
  return emb;
}

// simple domain extractor
function extractDomains(text = '') {
  const matches = (text || '').match(/https?:\/\/[^)\]\s]+/gi) || [];
  return matches.map(m => {
    try { return new URL(m).hostname.toLowerCase(); } catch (e) { return null; }
  }).filter(Boolean);
}

// check if a domain matches any pattern (substring or exact)
function domainMatches(domain, patterns = []) {
  if (!domain) return false;
  return patterns.some(p => (p && domain.includes(p.toLowerCase())));
}

// language detection stub (lightweight)
function detectLanguageSimple(text = '') {
  const t = (text || '').toLowerCase();
  if (!t) return 'unknown';
  // naive heuristics
  if (t.includes(' the ') || t.includes(' and ') || t.includes(' is ')) return 'en';
  if (t.includes(' el ') || t.includes(' la ') || t.includes(' que ') || t.includes(' y ')) return 'es';
  if (t.includes(' le ') || t.includes(' la ') || t.includes(' et ') || t.includes(' est ')) return 'fr';
  return 'unknown';
}

// ----------------------------- PERSPECTIVE API (text) -----------------------------
/**
 * analyzeTextPerspective(text)
 *  - returns a map of attribute -> score (0.0 - 1.0)
 *  - uses exponential backoff + retries
 *  - logs failure context
 */
async function analyzeTextPerspective(text) {
  if (!PERSPECTIVE_KEY) return null;
  // small optimization: if text is too short, skip
  if (!text || text.length < 4) return null;
  const url = `https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze?key=${PERSPECTIVE_KEY}`;
  const payload = {
    comment: { text },
    languages: ['en'],
    requestedAttributes: {
      TOXICITY: {},
      SEVERE_TOXICITY: {},
      INSULT: {},
      IDENTITY_ATTACK: {},
      THREAT: {},
      SEXUALLY_EXPLICIT: {},
    }
  };
  try {
    const result = await withRetries(async () => {
      const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      if (!res.ok) {
        const body = await res.text().catch(() => '');
        const e = new Error(`Perspective HTTP ${res.status}`);
        e.status = res.status;
        e.body = body;
        throw e;
      }
      return await res.json();
    }, { attempts: 4, baseMs: 500 });
    // parse into simpler map
    const out = {};
    const attr = result.attributeScores || {};
    Object.keys(attr).forEach(k => {
      const v = attr[k];
      out[k] = (v && v.summaryScore && typeof v.summaryScore.value === 'number') ? v.summaryScore.value : 0.0;
    });
    return out;
  } catch (e) {
    console.warn('Perspective analyze failed', { message: e.message, text_preview: text.slice(0, 200) });
    return null;
  }
}

// ----------------------------- GOOGLE VISION SAFESEARCH (image) -----------------------------
/**
 * analyzeImageSafeSearch(base64)
 *  - Uses Google Vision SafeSearch via REST
 *  - Caches results by SHA1(base64)
 *  - Retries with exponential backoff
 *  - Returns safeSearchAnnotation or null
 */
async function analyzeImageSafeSearch(base64) {
  if (!GOOGLE_VISION_KEY) return null;
  if (!base64) return null;
  const sha = sha1Base64(base64);
  const cached = getVisionCache(sha);
  if (cached) return cached;
  const url = `https://vision.googleapis.com/v1/images:annotate?key=${GOOGLE_VISION_KEY}`;
  const payload = {
    requests: [
      {
        image: { content: base64 },
        features: [{ type: 'SAFE_SEARCH_DETECTION' }]
      }
    ]
  };
  try {
    const result = await withRetries(async () => {
      const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      if (!res.ok) {
        const body = await res.text().catch(() => '');
        const e = new Error(`Vision HTTP ${res.status}`);
        e.status = res.status;
        e.body = body;
        throw e;
      }
      return await res.json();
    }, { attempts: 4, baseMs: 600 });
    const resp = (result.responses && result.responses[0] && result.responses[0].safeSearchAnnotation) || null;
    if (resp) setVisionCache(sha, resp);
    return resp;
  } catch (e) {
    console.warn('Vision analyze failed', { message: e.message });
    return null;
  }
}

// helper to fetch a url and return base64 content (size caution: large images will be fetched — ensure your host cares)
async function fetchUrlToBase64(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    const buf = await res.arrayBuffer();
    return Buffer.from(buf).toString('base64');
  } catch (e) {
    return null;
  }
}

// ----------------------------- MODERATION ACTIONS (warn/delete/mute/kick/ban) -----------------------------
/**
 * performAction(client, guildId, userId, actionString, context)
 *  - actionString supports combinations separated by '+', e.g. "delete+warn+temp_mute:300"
 *  - context may include messageObj (discord message), reason, rawScores, visionResp
 *  - this function tries to do the actions in a best-effort manner and logs infractions to DB
 */
async function performAction(client, guildId, userId, actionString, context = {}) {
  const cfg = getGuildConfig(guildId);
  const actions = (actionString || 'warn').split('+').map(a => a.trim()).filter(Boolean);
  const meta = { context, timestamp: nowIso() };
  for (const a of actions) {
    try {
      if (a.startsWith('temp_mute')) {
        const sec = a.includes(':') ? parseInt(a.split(':')[1]) || 300 : 300;
        // Prefer built-in timeout if available, else create or use mute role
        if (client) {
          try {
            const guild = await client.guilds.fetch(guildId).catch(() => null);
            if (guild) {
              const member = await guild.members.fetch(userId).catch(() => null);
              if (member) {
                // Try member.timeout (discord.js v14)
                try {
                  await member.timeout(sec * 1000, `AutoMod: ${context.reason || 'temp_mute'}`);
                } catch (e) {
                  // fallback to role
                  let muteRole = null;
                  if (cfg.muteRoleId) {
                    muteRole = await guild.roles.fetch(cfg.muteRoleId).catch(() => null);
                  }
                  if (!muteRole) {
                    // create role and set channel overwrite best-effort
                    muteRole = await guild.roles.create({ name: 'Muted', reason: 'AutoMod created mute role' }).catch(() => null);
                    if (muteRole) {
                      cfg.muteRoleId = muteRole.id;
                      setGuildConfig(guildId, cfg);
                      // set channel overwrites to deny SendMessages (best-effort)
                      for (const ch of guild.channels.cache.values()) {
                        if (ch.type === ChannelType.GuildText || ch.type === ChannelType.GuildForum) {
                          try {
                            await ch.permissionOverwrites.edit(muteRole, { SendMessages: false, AddReactions: false });
                          } catch (e) {
                            // ignore errors for channels we don't have perms on
                          }
                        }
                      }
                    }
                  }
                  if (muteRole) {
                    await member.roles.add(muteRole, `AutoMod: temp mute ${sec}s`);
                    // record unmute time in config
                    const unmuteAt = new Date(Date.now() + sec * 1000).toISOString();
                    cfg.tempMutes = cfg.tempMutes || [];
                    cfg.tempMutes.push({ userId, unmuteAt, reason: context.reason || 'temp_mute' });
                    setGuildConfig(guildId, cfg);
                  }
                }
              }
            }
          } catch (e) {
            // ignore
          }
        }
        addInfraction(guildId, userId, null, 'temp_mute', context.reason || 'AutoMod temp_mute', meta);
      } else if (a === 'delete') {
        if (context.messageObj && typeof context.messageObj.delete === 'function') {
          try { await context.messageObj.delete().catch(() => {}); } catch (e) {}
        }
        addInfraction(guildId, userId, null, 'delete', context.reason || 'AutoMod delete', meta);
        // send to log channel
        if (client) {
          const embed = buildEmbed({
            title: 'Message Deleted',
            description: `A message by <@${userId}> was deleted by AutoMod.`,
            fields: [ { name: 'Reason', value: context.reason || 'delete' }, { name: 'Category', value: context.category || 'unknown' } ],
            color: COLORS.warning
          });
          await sendToGuildLog(client, guildId, embed, userId);
        }
      } else if (a === 'warn') {
        // DM the user (best-effort)
        if (client) {
          try {
            const guild = await client.guilds.fetch(guildId).catch(() => null);
            if (guild) {
              const member = await guild.members.fetch(userId).catch(() => null);
              if (member) {
                await member.send({ embeds: [ buildEmbed({ title: 'You received a warning', description: `You were warned in ${guild.name}.\n\nReason: ${context.reason || 'AutoMod'} `, color: COLORS.warning }) ] }).catch(() => {});
              }
            }
          } catch (e) { /* ignore DM failures */ }
        }
        addInfraction(guildId, userId, null, 'warn', context.reason || 'AutoMod warn', meta);
        if (client) {
          const embed = buildEmbed({ title: 'User warned', description: `<@${userId}> was warned by AutoMod.`, color: COLORS.info });
          await sendToGuildLog(client, guildId, embed, userId);
        }
      } else if (a === 'kick') {
        if (client) {
          try {
            const guild = await client.guilds.fetch(guildId).catch(() => null);
            if (guild) {
              await guild.members.kick(userId, `AutoMod: ${context.reason || 'kick'}`).catch(() => {});
              addInfraction(guildId, userId, null, 'kick', context.reason || 'AutoMod kick', meta);
              const embed = buildEmbed({ title: 'User kicked', description: `<@${userId}> was kicked by AutoMod.`, color: COLORS.danger });
              await sendToGuildLog(client, guildId, embed, userId);
            }
          } catch (e) {}
        } else {
          addInfraction(guildId, userId, null, 'kick', context.reason || 'AutoMod kick (no client)', meta);
        }
      } else if (a === 'ban') {
        if (client) {
          try {
            const guild = await client.guilds.fetch(guildId).catch(() => null);
            if (guild) {
              await guild.bans.create(userId, { reason: `AutoMod: ${context.reason || 'ban'}` }).catch(() => {});
              addInfraction(guildId, userId, null, 'ban', context.reason || 'AutoMod ban', meta);
              const embed = buildEmbed({ title: 'User banned', description: `<@${userId}> was banned by AutoMod.`, color: COLORS.danger });
              await sendToGuildLog(client, guildId, embed, userId);
            }
          } catch (e) {}
        } else {
          addInfraction(guildId, userId, null, 'ban', context.reason || 'AutoMod ban (no client)', meta);
        }
      } else {
        // unknown action — ignore but log
        console.warn('Unknown action string part', a);
      }
    } catch (e) {
      console.warn('performAction caught error for action', a, 'err:', e && e.message);
    }
  }
}

// ----------------------------- GUILD LOGS (nice embeds + interactive buttons) -----------------------------
/**
 * sendToGuildLog(client, guildId, embed, targetUserId)
 *  - sends a mod log embed to the configured log channel
 *  - attaches moderator buttons with custom IDs so moderators can reactively take action
 */
async function sendToGuildLog(client, guildId, embed, targetUserId = null) {
  try {
    const cfg = getGuildConfig(guildId);
    if (!cfg.logChannelId) return;
    const guild = await client.guilds.fetch(guildId).catch(() => null);
    if (!guild) return;
    const ch = await guild.channels.fetch(cfg.logChannelId).catch(() => null);
    if (!ch || !ch.isTextBased()) return;
    // build action buttons
    const row = new ActionRowBuilder().addComponents(
      new ButtonBuilder().setCustomId(`mod:warn:${guildId}:${targetUserId || '0'}`).setLabel('Warn').setStyle(ButtonStyle.Primary),
      new ButtonBuilder().setCustomId(`mod:temp_mute:${guildId}:${targetUserId || '0'}`).setLabel('Temp Mute').setStyle(ButtonStyle.Secondary),
      new ButtonBuilder().setCustomId(`mod:delete:${guildId}:${targetUserId || '0'}`).setLabel('Delete Msg').setStyle(ButtonStyle.Danger),
      new ButtonBuilder().setCustomId(`mod:kick:${guildId}:${targetUserId || '0'}`).setLabel('Kick').setStyle(ButtonStyle.Danger),
      new ButtonBuilder().setCustomId(`mod:ban:${guildId}:${targetUserId || '0'}`).setLabel('Ban').setStyle(ButtonStyle.Danger)
    );
    await ch.send({ embeds: [embed], components: [row] }).catch(e => console.warn('sendToGuildLog send failed', e && e.message));
  } catch (e) {
    console.warn('sendToGuildLog error', e && e.message);
  }
}

// ----------------------------- TRIGGERS ENGINE (fallback, DB-stored) -----------------------------
/**
 * Trigger object format:
 * {
 *   id: string (uuid),
 *   name: string,
 *   trigger_type: 'contains'|'regex'|'invite'|'link'|'keyword',
 *   pattern: string,
 *   action: string e.g. 'delete+warn' or 'temp_mute:60+warn',
 *   enabled: boolean,
 *   created_by: 'userId',
 *   created_at: iso
 * }
 *
 * We provide helper functions to add/edit/delete triggers, and a function to test a message against triggers.
 */

function generateId(prefix = '') {
  return prefix + crypto.randomBytes(6).toString('hex');
}

function addTrigger(guildId, triggerObj) {
  const cfg = getGuildConfig(guildId);
  cfg.automodTriggers = cfg.automodTriggers || [];
  // assign id and timestamps
  triggerObj.id = triggerObj.id || generateId('t_');
  triggerObj.created_at = triggerObj.created_at || nowIso();
  cfg.automodTriggers.push(triggerObj);
  setGuildConfig(guildId, cfg);
  return triggerObj;
}
function editTrigger(guildId, triggerId, updates) {
  const cfg = getGuildConfig(guildId);
  cfg.automodTriggers = cfg.automodTriggers || [];
  const idx = cfg.automodTriggers.findIndex(t => t.id === triggerId);
  if (idx === -1) return null;
  cfg.automodTriggers[idx] = { ...cfg.automodTriggers[idx], ...updates, updated_at: nowIso() };
  setGuildConfig(guildId, cfg);
  return cfg.automodTriggers[idx];
}
function removeTrigger(guildId, triggerId) {
  const cfg = getGuildConfig(guildId);
  cfg.automodTriggers = cfg.automodTriggers || [];
  const before = cfg.automodTriggers.length;
  cfg.automodTriggers = cfg.automodTriggers.filter(t => t.id !== triggerId);
  setGuildConfig(guildId, cfg);
  return before - cfg.automodTriggers.length;
}
function listTriggers(guildId) {
  const cfg = getGuildConfig(guildId);
  return (cfg.automodTriggers || []).slice();
}

// test message against triggers — returns matched trigger or null
function testTriggers(guildId, content) {
  const cfg = getGuildConfig(guildId);
  const triggers = cfg.automodTriggers || [];
  const text = (content || '').toLowerCase();
  for (const t of triggers) {
    if (!t.enabled) continue;
    try {
      if (t.trigger_type === 'contains' || t.trigger_type === 'keyword') {
        const pats = (t.pattern || '').split(',').map(p => p.trim().toLowerCase()).filter(Boolean);
        for (const p of pats) if (text.includes(p)) return t;
      } else if (t.trigger_type === 'regex') {
        const re = new RegExp(t.pattern, 'i');
        if (re.test(content)) return t;
      } else if (t.trigger_type === 'invite') {
        if (content.includes('discord.gg/') || content.includes('discord.com/invite/')) return t;
      } else if (t.trigger_type === 'link') {
        const domains = extractDomains(content);
        for (const d of domains) {
          if (domainMatches(d, (t.pattern || '').split(',').map(s => s.trim().toLowerCase()))) return t;
        }
      } else {
        // unknown trigger type: fallback to simple substring
        if ((t.pattern || '') && content.toLowerCase().includes((t.pattern || '').toLowerCase())) return t;
      }
    } catch (e) {
      console.warn('Error testing trigger', t.id, e && e.message);
    }
  }
  return null;
}

// ----------------------------- SPAM ENGINE (per-guild counters + escalation) -----------------------------
/**
 * We maintain rolling arrays of timestamps (seconds) per guild+user.
 * The procedure:
 *  - On each message, fetch timestamps, append now, remove old ones outside window
 *  - If count >= threshold => perform initial spam action (delete+warn)
 *  - If repeated within escalation counts, escalate (temp_mute -> longer mute -> kick)
 *
 * The guild config has spamThreshold: { messages, seconds, escalations: [ {count, action}, ... ] }
 */

function recordMessageForSpam(guildId, userId) {
  const cfg = getGuildConfig(guildId);
  const thr = cfg.spamThreshold || { messages: 5, seconds: 8, escalations: [ {count:3, action:'temp_mute:60'} ] };
  const now = Math.floor(Date.now() / 1000);
  let arr = getSpamTimestamps(guildId, userId) || [];
  // remove older than window
  const windowStart = now - (thr.seconds || 8);
  arr = arr.filter(ts => ts >= windowStart);
  arr.push(now);
  setSpamTimestamps(guildId, userId, arr);
  return { count: arr.length, windowStart, windowSeconds: thr.seconds };
}

function clearSpamForUser(guildId, userId) {
  clearSpamTimestamps(guildId, userId);
}

// determine spam action (if any) — returns null or {action, matchedEscalation}
function determineSpamAction(guildId, count) {
  const cfg = getGuildConfig(guildId);
  const thr = cfg.spamThreshold || { messages: 5, seconds: 8, escalations: [ {count:3, action:'temp_mute:60'} ] };
  if (count >= (thr.messages || 5)) {
    // base spam action
    return { action: 'delete+warn', reason: `spam:${count}msgs` };
  }
  // check escalations
  const esc = thr.escalations || [];
  // choose highest matching count
  let chosen = null;
  for (const e of esc) {
    if (count >= e.count) {
      if (!chosen || e.count > chosen.count) chosen = e;
    }
  }
  if (chosen) return { action: chosen.action, reason: `spam_escalation:${count}` };
  return null;
}

// ----------------------------- NATIVE DISCORD AUTOMOD SYNC -----------------------------
/**
 * We implement create/read/update/delete of native AutoMod rules via Discord's REST API.
 * Because native rules are fairly structured and require precise schemas (filters, actions),
 * we provide a translator that maps our fallback triggers to Discord AutoMod rule objects.
 *
 * Steps for a sync run:
 *  - Read all existing guild automod rules via REST (GET /guilds/{guild.id}/auto-moderation/rules)
 *  - Compare to our desired set (derived from fallback triggers, banned words, links blacklist)
 *  - Present a diff as preview embed; if user confirms "Sync now", perform creates/updates/deletes
 *
 * Note: Creating automod rules requires the bot to have the MANAGE_GUILD permission and proper scope
 * (and Discord sometimes restricts what bots can set depending on ownership). This module attempts a best-effort sync
 * and reports any errors back to the dashboard output.
 */

// helper: build automod rule payload from our trigger
function translateTriggerToAutoModRule(trigger) {
  // This translator handles several basic types:
  //  - contains/keyword -> keyword filter
  //  - regex -> keyword filter with regex? (Discord automod supports keyword and mention spam, not arbitrary regex)
  //  - invite -> spam filter (invites)
  //  - link -> keyword filter for domains
  // We'll map to discord's AutoMod "keyword_filter" where possible.
  // NOTE: Discord's automod rule schema expects:
  // {
  //   name, event_type: 1 (message send),
  //   trigger_metadata: { keywords: [], allow_list: [], regex_patterns: [] },
  //   actions: [ ... ],
  //   enabled: true,
  //   exempt_roles: [],
  //   exempt_channels: []
  // }
  const name = trigger.name || `fallback-${trigger.id}`;
  const event_type = 1; // MESSAGE_SEND
  const trigger_metadata = {};
  if (trigger.trigger_type === 'contains' || trigger.trigger_type === 'keyword') {
    const keywords = (trigger.pattern || '').split(',').map(s => s.trim()).filter(Boolean).slice(0, 50);
    trigger_metadata.keywords = keywords;
  } else if (trigger.trigger_type === 'invite') {
    // Discord AutoMod supports detecting invites via a type of filter; we'll use keyword with discord.gg and discord.com/invite patterns
    trigger_metadata.keywords = ['discord.gg', 'discord.com/invite'];
  } else if (trigger.trigger_type === 'link') {
    const keywords = (trigger.pattern || '').split(',').map(s => s.trim()).filter(Boolean);
    trigger_metadata.keywords = keywords;
  } else if (trigger.trigger_type === 'regex') {
    // Only use regex if pattern seems small and safe — discord accepts regex_patterns in trigger_metadata
    trigger_metadata.regex_patterns = [trigger.pattern];
  } else {
    trigger_metadata.keywords = [(trigger.pattern || '').slice(0, 50)];
  }
  // actions mapping (we pick the first action that fits automod)
  // AutoMod supports actions like BLOCK_MESSAGE, SEND_ALERT_MESSAGE, TIMEOUT, BLOCK_MESSAGE (block), etc.
  // We'll map:
  // - 'delete' -> BLOCK_MESSAGE
  // - 'warn' -> SEND_ALERT_MESSAGE (alert to mod channel)
  // - 'temp_mute:seconds' -> TIMEOUT (we must convert seconds to ms)
  const actions = [];
  const parts = (trigger.action || 'warn').split('+').map(x => x.trim());
  for (const p of parts) {
    if (p === 'delete') {
      actions.push({ type: 1, metadata: {} }); // BLOCK_MESSAGE
    } else if (p === 'warn') {
      // Send alert: requires a channel id in 'metadata', but the API supports sending an alert message to the moderation system
      actions.push({ type: 2, metadata: { channel_id: null } }); // we will later fill in channel id in sync routine if a log channel exists
    } else if (p.startsWith('temp_mute')) {
      const seconds = p.includes(':') ? parseInt(p.split(':')[1]) || 300 : 300;
      // Discord automod supports timeout as action type 3 with metadata.duration_seconds
      actions.push({ type: 3, metadata: { duration_seconds: seconds } });
    } else {
      // fallback: alert
      actions.push({ type: 2, metadata: { channel_id: null } });
    }
  }
  // Build base object
  return {
    name,
    event_type,
    trigger_metadata,
    actions,
    enabled: trigger.enabled !== false,
    exempt_roles: trigger.exempt_roles || [],
    exempt_channels: trigger.exempt_channels || []
  };
}

/**
 * fetchGuildAutoModRules(client, guildId)
 *  - returns an array of rules from Discord REST via client's application id
 *  - uses REST client for raw endpoints (safer for automod rules as discord.js may not have wrapper)
 */
async function fetchGuildAutoModRulesREST(client, guildId) {
  if (!client || !client.user) throw new Error('Discord client not ready');
  const rest = new REST({ version: '10' }).setToken(BOT_TOKEN);
  try {
    const appId = client.user.id;
    const url = Routes.guildAutoModerationRules(guildId);
    const res = await rest.get(url);
    // res is an array of rules
    return res;
  } catch (e) {
    throw new Error(`fetchGuildAutoModRulesREST failed: ${e && e.message}`);
  }
}

// create/update/delete rule via REST
async function createAutoModRuleREST(client, guildId, rulePayload) {
  const rest = new REST({ version: '10' }).setToken(BOT_TOKEN);
  try {
    const url = Routes.guildAutoModerationRules(guildId);
    const res = await rest.post(url, { body: rulePayload });
    return res;
  } catch (e) {
    throw new Error(`createAutoModRuleREST failed: ${e && e.message}`);
  }
}
async function editAutoModRuleREST(client, guildId, ruleId, rulePayload) {
  const rest = new REST({ version: '10' }).setToken(BOT_TOKEN);
  try {
    const url = Routes.guildAutoModerationRule(guildId, ruleId);
    const res = await rest.patch(url, { body: rulePayload });
    return res;
  } catch (e) {
    throw new Error(`editAutoModRuleREST failed: ${e && e.message}`);
  }
}
async function deleteAutoModRuleREST(client, guildId, ruleId) {
  const rest = new REST({ version: '10' }).setToken(BOT_TOKEN);
  try {
    const url = Routes.guildAutoModerationRule(guildId, ruleId);
    const res = await rest.delete(url);
    return res;
  } catch (e) {
    throw new Error(`deleteAutoModRuleREST failed: ${e && e.message}`);
  }
}

/**
 * syncFallbackToNativeAutoMod(client, guildId)
 *  - builds desired set from DB fallback triggers and banned words and links blacklist
 *  - fetches existing native rules and computes diff (create/update/delete)
 *  - returns preview object { toCreate:[], toUpdate:[], toDelete:[] }
 *  - actual execution should be performed only when requested (to avoid surprises)
 */
async function syncFallbackToNativeAutoModPreview(client, guildId) {
  // Build desired rules from triggers
  const triggers = listTriggers(guildId);
  // Also include banned words as a single rule where possible
  const cfg = getGuildConfig(guildId);
  const desired = [];
  // Add triggers
  for (const t of triggers) {
    const r = translateTriggerToAutoModRule(t);
    // If action included alert/warn we want to set the metadata.channel_id to the guild log channel if present
    if (r.actions && r.actions.length) {
      r.actions = r.actions.map(a => {
        if (a.type === 2) { // alert
          return { ...a, metadata: { channel_id: cfg.logChannelId || null } };
        }
        return a;
      });
    }
    desired.push({ sourceTriggerId: t.id, name: r.name, payload: r });
  }
  // add banned words as a rule if exist
  if ((cfg.bannedWords || []).length > 0) {
    const bw = cfg.bannedWords.slice(0, 100); // limited
    const name = 'fallback-banned-words';
    desired.push({
      sourceTriggerId: `bannedwords`,
      name,
      payload: {
        name,
        event_type: 1,
        trigger_metadata: { keywords: bw },
        actions: [{ type: 1, metadata: {} }], // block message
        enabled: true,
        exempt_roles: [],
        exempt_channels: []
      }
    });
  }
  // Add links blacklist as rule
  if ((cfg.linksBlacklist || []).length > 0) {
    const lbs = cfg.linksBlacklist.slice(0, 50);
    const name = 'fallback-links-blacklist';
    desired.push({
      sourceTriggerId: `links_blacklist`,
      name,
      payload: {
        name,
        event_type: 1,
        trigger_metadata: { keywords: lbs },
        actions: [{ type: 1, metadata: {} }], // block
        enabled: true,
        exempt_roles: [],
        exempt_channels: []
      }
    });
  }

  // fetch existing native rules
  let existing = [];
  try {
    existing = await fetchGuildAutoModRulesREST(client, guildId);
  } catch (e) {
    // propagate error
    throw e;
  }

  // Build maps by name for easy diff
  const existingByName = new Map();
  for (const ex of existing) existingByName.set(ex.name, ex);

  // Determine create/update/delete
  const toCreate = [];
  const toUpdate = [];
  const toKeep = new Set();
  for (const d of desired) {
    const name = d.name;
    const payload = d.payload;
    if (!existingByName.has(name)) {
      toCreate.push({ desired: d });
    } else {
      const existingRule = existingByName.get(name);
      // Compare key fields: trigger_metadata and actions
      // For simplicity we'll do a JSON compare of specific fields
      const cleanExisting = {
        trigger_metadata: existingRule.trigger_metadata,
        actions: existingRule.actions
      };
      const cleanDesired = {
        trigger_metadata: payload.trigger_metadata,
        actions: payload.actions
      };
      if (safeStringify(cleanExisting) !== safeStringify(cleanDesired)) {
        toUpdate.push({ existing: existingRule, desired: d });
      } else {
        toKeep.add(existingRule.id);
      }
    }
  }
  // any existing not in keep and not created/updated should be considered for deletion (but we'll be cautious)
  const toDelete = [];
  for (const ex of existing) {
    if (!toKeep.has(ex.id) && !desired.some(d => d.name === ex.name)) {
      // only delete rules that were created by our sync before — we look for "fallback-" prefix or our known names
      if (ex.name.startsWith('fallback-') || ex.name === 'fallback-banned-words' || ex.name === 'fallback-links-blacklist' || ex.name.startsWith('fallback-')) {
        toDelete.push(ex);
      }
    }
  }
  return { toCreate, toUpdate, toDelete, existingCount: existing.length, desiredCount: desired.length };
}

// Execute the sync (dangerous operation) — returns result summary
async function executeSyncToNativeAutoMod(client, guildId, preview) {
  const results = { created: [], updated: [], deleted: [], errors: [] };
  // perform creates
  for (const c of preview.toCreate) {
    try {
      const res = await createAutoModRuleREST(client, guildId, c.desired.payload);
      results.created.push(res);
    } catch (e) {
      results.errors.push({ action: 'create', error: e.message, item: c.desired.name });
    }
  }
  for (const u of preview.toUpdate) {
    try {
      const ruleId = u.existing.id;
      const res = await editAutoModRuleREST(client, guildId, ruleId, u.desired.payload);
      results.updated.push(res);
    } catch (e) {
      results.errors.push({ action: 'update', error: e.message, item: u.desired.name });
    }
  }
  for (const d of preview.toDelete) {
    try {
      await deleteAutoModRuleREST(client, guildId, d.id);
      results.deleted.push(d.id);
    } catch (e) {
      results.errors.push({ action: 'delete', error: e.message, item: d.name });
    }
  }
  return results;
}

// ----------------------------- DASHBOARD COMMAND: UI & INTERACTIONS -----------------------------
/**
 * We'll register a single slash command: /automod dashboard
 * - Presents an embed snapshot
 * - Select menu to choose section
 * - Buttons & modals to edit values
 *
 * Interaction flow:
 * 1. User runs /automod dashboard -> bot sends ephemeral message with embed + select
 * 2. User selects a section -> we update the ephemeral message with relevant UI components
 * 3. For actions requiring input, we present a modal. Modal submits are handled by interactionCreate events.
 *
 * We'll implement robust handlers for:
 *  - Config toggles
 *  - Add/edit/remove triggers via modal
 *  - Sync preview & execution
 *  - Spam stats & controls
 */

// Build slash command
function buildAutomodCommand() {
  return new SlashCommandBuilder()
    .setName('automod')
    .setDescription('Open the AutoMod Neo dashboard (interactive)')
    .addSubcommand(s => s.setName('dashboard').setDescription('Open the interactive AutoMod dashboard'));
}

// Helper to create dashboard snapshot embed
function buildDashboardEmbed(guildId) {
  const cfg = getGuildConfig(guildId);
  const fields = [
    { name: 'Log channel', value: cfg.logChannelId ? `<#${cfg.logChannelId}>` : 'Not set', inline: true },
    { name: 'NSFW scan', value: String(!!cfg.nsfwScanEnabled), inline: true },
    { name: 'AutoMod sync', value: String(!!cfg.automodSync), inline: true },
    { name: 'Triggers', value: `${(cfg.automodTriggers || []).length} fallback triggers`, inline: true },
    { name: 'Banned words', value: (cfg.bannedWords || []).slice(0, 10).join(', ') || 'None', inline: false }
  ];
  return buildEmbed({ title: `${EMOJI.spark} AutoMod • Dashboard`, description: 'Neo-dark control panel — pick a section from the menu.', fields, color: COLORS.background });
}

// helper: dashboard action row (select menu)
function buildDashboardSelect(guildId) {
  const menu = new StringSelectMenuBuilder()
    .setCustomId(`automod:menu:${guildId}`)
    .setPlaceholder('Choose a section to manage')
    .addOptions(
      { label: 'Configuration', value: 'config', description: 'View and edit general settings', emoji: '⚙️' },
      { label: 'Triggers', value: 'triggers', description: 'View/add/remove fallback triggers', emoji: '⚠️' },
      { label: 'AI Thresholds', value: 'ai', description: 'Adjust Perspective & Vision thresholds', emoji: '🧠' },
      { label: 'Spam & Escalation', value: 'spam', description: 'Configure spam detection & escalations', emoji: '⚡' },
      { label: 'Infractions & Logs', value: 'logs', description: 'Inspect recent infractions', emoji: '📜' },
      { label: 'AutoMod Sync', value: 'sync', description: 'Preview & sync fallback rules to Discord native AutoMod', emoji: EMOJI.sync }
    );
  return new ActionRowBuilder().addComponents(menu);
}

// ----------------------------- INTERACTION HANDLERS (for Discord client) -----------------------------
/**
 * handleInteraction(interaction, client)
 *  - Handles:
 *    - Slash command: open dashboard
 *    - SelectMenu: user navigations in dashboard
 *    - Button: actions (add trigger, remove, sync preview, sync execute, mod buttons)
 *    - ModalSubmit: adding/editing triggers, setting config values
 *
 * We put permission checks: only moderators (or server owner / admins) can perform config changes.
 */

/**
 * isModerator(member)
 *   checks if the member is guild owner, has ADMINISTRATOR, or has configured mod roles
 */
async function isModerator(member) {
  if (!member) return false;
  try {
    if (member.guild.ownerId === member.id) return true;
    if (member.permissions.has(PermissionsBitField.Flags.Administrator)) return true;
    const cfg = getGuildConfig(member.guild.id);
    const modRoleIds = cfg.modRoleIds || [];
    for (const r of member.roles.cache.values()) if (modRoleIds.includes(r.id)) return true;
    return false;
  } catch (e) { return false; }
}

// full interaction handler will be attached in startClient
async function handleInteraction(interaction, client) {
  try {
    // Slash command: /automod dashboard
    if (interaction.isChatInputCommand() && interaction.commandName === 'automod') {
      if (interaction.options.getSubcommand() === 'dashboard') {
        // require guild
        if (!interaction.guild) {
          await interaction.reply({ content: 'This command must be used in a guild.', ephemeral: true });
          return;
        }
        await interaction.deferReply({ ephemeral: true });
        const guildId = interaction.guildId;
        const embed = buildDashboardEmbed(guildId);
        const selectRow = buildDashboardSelect(guildId);
        await interaction.editReply({ embeds: [embed], components: [selectRow], ephemeral: true });
        return;
      }
    }

    // Select menu handler (dashboard navigation)
    if (interaction.isStringSelectMenu()) {
      const [prefix, type, guildId] = interaction.customId.split(':');
      if (prefix !== 'automod' || type !== 'menu') return;
      if (!interaction.member) {
        await interaction.reply({ content: 'Could not resolve member.', ephemeral: true }); return;
      }
      const chosen = interaction.values[0];
      // only interactive for the user who opened initial message — we don't check that to keep UX friendly
      // Section handling
      if (chosen === 'config') {
        // Build config embed + buttons
        const cfg = getGuildConfig(guildId);
        const embed = buildEmbed({
          title: `${EMOJI.shield} Configuration`,
          description: 'Quick toggles and settings for this server.',
          fields: [
            { name: 'Log channel', value: cfg.logChannelId ? `<#${cfg.logChannelId}>` : 'Not set', inline: true },
            { name: 'NSFW scanning', value: String(!!cfg.nsfwScanEnabled), inline: true },
            { name: 'AutoMod Sync', value: String(!!cfg.automodSync), inline: true },
          ],
          color: COLORS.info
        });
        const row = new ActionRowBuilder().addComponents(
          new ButtonBuilder().setCustomId(`automod:cfg_setlog:${guildId}`).setLabel('Set Log Channel').setStyle(ButtonStyle.Primary),
          new ButtonBuilder().setCustomId(`automod:cfg_toggle_nsfw:${guildId}`).setLabel(cfg.nsfwScanEnabled ? 'Disable NSFW' : 'Enable NSFW').setStyle(ButtonStyle.Secondary),
          new ButtonBuilder().setCustomId(`automod:cfg_toggle_sync:${guildId}`).setLabel(cfg.automodSync ? 'Disable Sync' : 'Enable Sync').setStyle(ButtonStyle.Secondary),
        );
        await interaction.update({ embeds: [embed], components: [row], ephemeral: true });
        return;
      } else if (chosen === 'triggers') {
        const cfg = getGuildConfig(guildId);
        const triggers = cfg.automodTriggers || [];
        const listText = triggers.slice(0, 25).map((t, idx) => `${idx+1}. **${t.name || '(no name)'}** • ${t.trigger_type} • \`${(t.pattern || '').slice(0,40)}\` -> \`${t.action}\``).join('\n') || 'No fallback triggers configured.';
        const embed = buildEmbed({ title: `${EMOJI.warn} Triggers & Rules`, description: listText, color: COLORS.warning });
        const row = new ActionRowBuilder().addComponents(
          new ButtonBuilder().setCustomId(`automod:trig_add:${guildId}`).setLabel('Add trigger').setStyle(ButtonStyle.Success),
          new ButtonBuilder().setCustomId(`automod:trig_edit:${guildId}`).setLabel('Edit trigger').setStyle(ButtonStyle.Primary),
          new ButtonBuilder().setCustomId(`automod:trig_remove:${guildId}`).setLabel('Remove trigger').setStyle(ButtonStyle.Danger),
        );
        await interaction.update({ embeds: [embed], components: [row], ephemeral: true });
        return;
      } else if (chosen === 'ai') {
        const cfg = getGuildConfig(guildId);
        const p = cfg.perspectiveThresholds || {};
        const v = cfg.visionThresholds || {};
        const pText = Object.entries(p).map(([k, v2]) => `• ${k}: threshold=${v2.threshold} -> action=${v2.action}`).join('\n') || 'No perspective thresholds configured.';
        const vText = Object.entries(v).map(([k, v2]) => `• ${k}: levels=[${(v2.levels||[]).join(',')}] -> action=${v2.action}`).join('\n') || 'No vision thresholds configured.';
        const embed = buildEmbed({ title: `${EMOJI.brain} AI Thresholds`, description: `${pText}\n\n${vText}`, color: COLORS.accent });
        const row = new ActionRowBuilder().addComponents(
          new ButtonBuilder().setCustomId(`automod:ai_edit:${guildId}`).setLabel('Edit thresholds').setStyle(ButtonStyle.Primary),
          new ButtonBuilder().setCustomId(`automod:ai_test:${guildId}`).setLabel('Run AI test').setStyle(ButtonStyle.Secondary)
        );
        await interaction.update({ embeds: [embed], components: [row], ephemeral: true });
        return;
      } else if (chosen === 'spam') {
        const cfg = getGuildConfig(guildId);
        const thr = cfg.spamThreshold || {};
        const embed = buildEmbed({ title: `${EMOJI.spark} Spam & Escalation`, description: `Messages: ${thr.messages || 5} in ${thr.seconds || 8}s\nEscalations:\n${(thr.escalations || []).map(e => `• ${e.count} => ${e.action}`).join('\n')}`, color: COLORS.info });
        const row = new ActionRowBuilder().addComponents(
          new ButtonBuilder().setCustomId(`automod:spam_clear:${guildId}`).setLabel('Clear spam counters').setStyle(ButtonStyle.Secondary),
          new ButtonBuilder().setCustomId(`automod:spam_test:${guildId}`).setLabel('Run spam test').setStyle(ButtonStyle.Primary)
        );
        await interaction.update({ embeds: [embed], components: [row], ephemeral: true });
        return;
      } else if (chosen === 'logs') {
        const rows = getRecentInfractions(guildId, 10);
        const text = rows.map(r => `#${r.id} • <@${r.user_id}> • ${r.action} • ${r.reason} • ${r.created_at}`).join('\n') || 'No infractions';
        const embed = buildEmbed({ title: `${EMOJI.logs} Infractions (recent)`, description: text, color: COLORS.warning });
        await interaction.update({ embeds: [embed], components: [], ephemeral: true });
        return;
      } else if (chosen === 'sync') {
        // produce a preview and show buttons to execute
        await interaction.deferReply({ ephemeral: true });
        try {
          const preview = await syncFallbackToNativeAutoModPreview(client, guildId);
          const embed = buildEmbed({
            title: `${EMOJI.sync} AutoMod Sync Preview`,
            description: `Existing native rules: ${preview.existingCount}\nDesired fallback rules: ${preview.desiredCount}\n\nTo create: ${preview.toCreate.length}\nTo update: ${preview.toUpdate.length}\nTo delete: ${preview.toDelete.length}`,
            fields: [
              { name: 'Create', value: preview.toCreate.map(c => `• ${c.desired.name}`).slice(0,10).join('\n') || 'None', inline: true },
              { name: 'Update', value: preview.toUpdate.map(u => `• ${u.desired.name}`).slice(0,10).join('\n') || 'None', inline: true },
              { name: 'Delete', value: preview.toDelete.map(d => `• ${d.name}`).slice(0,10).join('\n') || 'None', inline: true },
            ],
            color: COLORS.info
          });
          const row = new ActionRowBuilder().addComponents(
            new ButtonBuilder().setCustomId(`automod:sync_execute:${guildId}`).setLabel('Execute Sync').setStyle(ButtonStyle.Danger),
            new ButtonBuilder().setCustomId(`automod:sync_cancel:${guildId}`).setLabel('Cancel').setStyle(ButtonStyle.Secondary)
          );
          await interaction.followUp({ embeds: [embed], components: [row], ephemeral: true });
        } catch (e) {
          await interaction.followUp({ content: `Failed to preview sync: ${e && e.message}`, ephemeral: true });
        }
        return;
      }
    }

    // Button handlers
    if (interaction.isButton()) {
      const parts = interaction.customId.split(':');
      if (parts[0] === 'automod') {
        const action = parts[1];
        const guildId = parts[2];
        // ensure permission
        if (!interaction.member) {
          await interaction.reply({ content: 'Member context required.', ephemeral: true }); return;
        }
        if (!await isModerator(interaction.member)) {
          await interaction.reply({ content: 'Permission denied. You must be a configured moderator or admin/owner.', ephemeral: true }); return;
        }
        // handle actions
        if (action === 'cfg_setlog') {
          // show modal to ask channel id
          const modal = new ModalBuilder().setCustomId(`automod:modal_setlog:${guildId}`).setTitle('Set AutoMod Log Channel');
          const input = new TextInputBuilder().setCustomId('log_channel').setLabel('Channel ID or mention (e.g. #mod-logs)').setStyle(TextInputStyle.Short).setRequired(true);
          modal.addComponents(new ARBuilder().addComponents(input));
          await interaction.showModal(modal);
          return;
        } else if (action === 'cfg_toggle_nsfw') {
          const cfg = getGuildConfig(guildId);
          cfg.nsfwScanEnabled = !cfg.nsfwScanEnabled;
          setGuildConfig(guildId, cfg);
          await interaction.update({ content: `NSFW scanning is now ${cfg.nsfwScanEnabled}`, embeds: [], components: [], ephemeral: true });
          return;
        } else if (action === 'cfg_toggle_sync') {
          const cfg = getGuildConfig(guildId);
          cfg.automodSync = !cfg.automodSync;
          setGuildConfig(guildId, cfg);
          await interaction.update({ content: `AutoMod sync toggled -> ${cfg.automodSync}`, embeds: [], components: [], ephemeral: true });
          return;
        } else if (action === 'trig_add') {
          // show modal to add trigger
          const modal = new ModalBuilder().setCustomId(`automod:modal_addtrigger:${guildId}`).setTitle('Add fallback trigger');
          const nameInput = new TextInputBuilder().setCustomId('name').setLabel('Rule name').setStyle(TextInputStyle.Short).setPlaceholder('e.g. block-invites').setRequired(true);
          const typeInput = new TextInputBuilder().setCustomId('type').setLabel('Trigger type').setStyle(TextInputStyle.Short).setPlaceholder('contains|regex|invite|link').setRequired(true);
          const patternInput = new TextInputBuilder().setCustomId('pattern').setLabel('Pattern / keywords').setStyle(TextInputStyle.Paragraph).setPlaceholder('pattern or comma-separated keywords').setRequired(false);
          const actionInput = new TextInputBuilder().setCustomId('action').setLabel('Action').setStyle(TextInputStyle.Short).setPlaceholder('delete+warn or temp_mute:300').setRequired(true);
          modal.addComponents(new ARBuilder().addComponents(nameInput), new ARBuilder().addComponents(typeInput), new ARBuilder().addComponents(patternInput), new ARBuilder().addComponents(actionInput));
          await interaction.showModal(modal);
          return;
        } else if (action === 'trig_edit') {
          // show modal to choose trigger id and new values — simplified flow: ask for trigger id then open smaller modal later
          const modal = new ModalBuilder().setCustomId(`automod:modal_request_edit:${guildId}`).setTitle('Edit fallback trigger — step 1');
          const idInput = new TextInputBuilder().setCustomId('trigger_id').setLabel('Trigger ID (from list)').setStyle(TextInputStyle.Short).setRequired(true);
          modal.addComponents(new ARBuilder().addComponents(idInput));
          await interaction.showModal(modal);
          return;
        } else if (action === 'trig_remove') {
          const modal = new ModalBuilder().setCustomId(`automod:modal_remove:${guildId}`).setTitle('Remove fallback trigger');
          const idInput = new TextInputBuilder().setCustomId('trigger_id').setLabel('Trigger ID (from list)').setStyle(TextInputStyle.Short).setRequired(true);
          modal.addComponents(new ARBuilder().addComponents(idInput));
          await interaction.showModal(modal);
          return;
        } else if (action === 'ai_edit') {
          // show modal to edit perspective thresholds — simplified: provide JSON body (admin)
          const modal = new ModalBuilder().setCustomId(`automod:modal_ai_edit:${guildId}`).setTitle('Edit AI thresholds (JSON)');
          const aiInput = new TextInputBuilder().setCustomId('ai_json').setLabel('Perspective thresholds JSON').setStyle(TextInputStyle.Paragraph).setPlaceholder(JSON.stringify(getGuildConfig(guildId).perspectiveThresholds, null, 2)).setRequired(true);
          modal.addComponents(new ARBuilder().addComponents(aiInput));
          await interaction.showModal(modal);
          return;
        } else if (action === 'ai_test') {
          // run a short sample test where we prompt the moderator for sample text via modal
          const modal = new ModalBuilder().setCustomId(`automod:modal_ai_test:${guildId}`).setTitle('AI Test — provide sample text');
          const sample = new TextInputBuilder().setCustomId('sample_text').setLabel('Sample text to analyze').setStyle(TextInputStyle.Paragraph).setRequired(true);
          modal.addComponents(new ARBuilder().addComponents(sample));
          await interaction.showModal(modal);
          return;
        } else if (action === 'spam_clear') {
          // clear all spam counters for this guild (caution)
          // We will clear spam counters table rows for the guild
          try {
            // prepare statement to delete all rows for guild
            db.prepare('DELETE FROM spam_counters WHERE guild_id = ?').run(guildId);
            await interaction.update({ content: 'Spam counters cleared for this server.', embeds: [], components: [], ephemeral: true });
          } catch (e) {
            await interaction.update({ content: 'Failed to clear spam counters: ' + e.message, ephemeral: true });
          }
          return;
        } else if (action === 'spam_test') {
          await interaction.update({ content: 'Spam test: please post several messages rapidly in any text channel to trigger detection (or use microservice scan).', ephemeral: true });
          return;
        } else if (action === 'sync_execute') {
          // execute full sync
          await interaction.deferReply({ ephemeral: true });
          try {
            const preview = await syncFallbackToNativeAutoModPreview(client, guildId);
            const result = await executeSyncToNativeAutoMod(client, guildId, preview);
            await interaction.editReply({ content: `Sync executed. Created: ${result.created.length}, Updated: ${result.updated.length}, Deleted: ${result.deleted.length}. Errors: ${result.errors.length}`, ephemeral: true });
            // log results to guild
            const embed = buildEmbed({ title: 'AutoMod Sync executed', description: `Created: ${result.created.length}\nUpdated: ${result.updated.length}\nDeleted: ${result.deleted.length}\nErrors: ${result.errors.length}`, color: COLORS.accent });
            await sendToGuildLog(client, guildId, embed, null);
          } catch (e) {
            await interaction.editReply({ content: 'Sync failed: ' + e.message, ephemeral: true });
          }
          return;
        } else if (action === 'sync_cancel') {
          await interaction.update({ content: 'Sync canceled.', embeds: [], components: [], ephemeral: true });
          return;
        }
      }
      // moderator action buttons (from mod log embed)
      if (parts[0] === 'mod') {
        // customId like mod:warn:gId:userId
        const modAction = parts[1];
        const guildId = parts[2];
        const targetUserId = parts[3] && parts[3] !== '0' ? parts[3] : null;
        if (!await isModerator(interaction.member)) {
          await interaction.reply({ content: 'Permission denied.', ephemeral: true });
          return;
        }
        // Do the action
        if (!targetUserId) {
          await interaction.reply({ content: 'No target user set on this log.', ephemeral: true }); return;
        }
        if (modAction === 'warn') {
          // send DM and add infraction
          try {
            const g = await client.guilds.fetch(guildId);
            await g.members.fetch(targetUserId).then(m => m.send({ embeds: [buildEmbed({ title: 'Moderation: Warning', description: `You were warned by a moderator in ${g.name}.` })]) }).catch(()=>{});
            addInfraction(guildId, targetUserId, interaction.user.id, 'warn', 'Moderator manual warn');
            await interaction.reply({ content: `Warned <@${targetUserId}>.`, ephemeral: true });
          } catch (e) { await interaction.reply({ content: 'Failed to warn: ' + e.message, ephemeral: true }); }
          return;
        } else if (modAction === 'temp_mute') {
          try {
            const g = await client.guilds.fetch(guildId);
            const member = await g.members.fetch(targetUserId);
            await member.timeout(60*1000, `Moderator manual mute`);
            addInfraction(guildId, targetUserId, interaction.user.id, 'temp_mute', 'Moderator manual mute 60s');
            await interaction.reply({ content: `Temporarily muted <@${targetUserId}> for 60s.`, ephemeral: true });
          } catch (e) { await interaction.reply({ content: 'Failed to mute: ' + e.message, ephemeral: true }); }
          return;
        } else if (modAction === 'delete') {
          // We can't delete the original message from the embed easily; we record infraction
          addInfraction(guildId, targetUserId || 'unknown', interaction.user.id, 'delete', 'Manual deletion via mod log');
          await interaction.reply({ content: `Recorded delete action for <@${targetUserId}>.`, ephemeral: true });
          return;
        } else if (modAction === 'kick') {
          try {
            const g = await client.guilds.fetch(guildId);
            await g.members.kick(targetUserId, 'Moderator manual kick');
            addInfraction(guildId, targetUserId, interaction.user.id, 'kick', 'Manual kick');
            await interaction.reply({ content: `Kicked <@${targetUserId}>.`, ephemeral: true });
          } catch (e) { await interaction.reply({ content: 'Failed to kick: ' + e.message, ephemeral: true }); }
          return;
        } else if (modAction === 'ban') {
          try {
            const g = await client.guilds.fetch(guildId);
            await g.bans.create(targetUserId, { reason: 'Moderator manual ban' });
            addInfraction(guildId, targetUserId, interaction.user.id, 'ban', 'Manual ban');
            await interaction.reply({ content: `Banned <@${targetUserId}>.`, ephemeral: true });
          } catch (e) { await interaction.reply({ content: 'Failed to ban: ' + e.message, ephemeral: true }); }
          return;
        }
      }
    }

    // Modal submit handling (adding/editing triggers, setting log channel, AI test, etc.)
    if (interaction.isModalSubmit && interaction.customId.startsWith('automod:modal_')) {
      const parts = interaction.customId.split(':');
      const modalAction = parts[1];
      const guildId = parts[2];
      if (!await isModerator(interaction.member)) {
        await interaction.reply({ content: 'Permission denied for modal action.', ephemeral: true });
        return;
      }
      if (modalAction === 'addtrigger') {
        // read fields
        const name = interaction.fields.getTextInputValue('name');
        const trigger_type = interaction.fields.getTextInputValue('type');
        const pattern = interaction.fields.getTextInputValue('pattern') || '';
        const actionVal = interaction.fields.getTextInputValue('action') || 'warn';
        const t = {
          id: generateId('t_'),
          name,
          trigger_type,
          pattern,
          action: actionVal,
          enabled: true,
          created_by: interaction.user.id,
          created_at: nowIso()
        };
        addTrigger(guildId, t);
        await interaction.reply({ content: `Trigger "${name}" added.`, ephemeral: true });
        return;
      } else if (modalAction === 'modal_setlog') {
        const chinput = interaction.fields.getTextInputValue('log_channel');
        // parse channel mention or id
        const m = chinput.match(/<#(\d+)>/);
        let channelId = null;
        if (m) channelId = m[1];
        else if (!isNaN(Number(chinput))) channelId = chinput;
        if (!channelId) {
          await interaction.reply({ content: 'Invalid channel id or mention. Please provide a channel mention or ID.', ephemeral: true }); return;
        }
        const cfg = getGuildConfig(guildId);
        cfg.logChannelId = channelId;
        setGuildConfig(guildId, cfg);
        await interaction.reply({ content: `Log channel set to <#${channelId}>.`, ephemeral: true });
        return;
      } else if (modalAction === 'modal_request_edit') {
        const id = interaction.fields.getTextInputValue('trigger_id');
        const cfg = getGuildConfig(guildId);
        const trig = (cfg.automodTriggers || []).find(t => t.id === id);
        if (!trig) {
          await interaction.reply({ content: `Trigger id ${id} not found.`, ephemeral: true }); return;
        }
        // open another modal with prefilled values to edit
        const modal = new ModalBuilder().setCustomId(`automod:modal_edit:${guildId}:${id}`).setTitle('Edit Trigger');
        const nameInput = new TextInputBuilder().setCustomId('name').setLabel('Name').setStyle(TextInputStyle.Short).setValue(trig.name || '').setRequired(true);
        const typeInput = new TextInputBuilder().setCustomId('type').setLabel('Type').setStyle(TextInputStyle.Short).setValue(trig.trigger_type || '').setRequired(true);
        const patternInput = new TextInputBuilder().setCustomId('pattern').setLabel('Pattern').setStyle(TextInputStyle.Paragraph).setValue(trig.pattern || '').setRequired(false);
        const actionInput = new TextInputBuilder().setCustomId('action').setLabel('Action').setStyle(TextInputStyle.Short).setValue(trig.action || '').setRequired(true);
        modal.addComponents(new ARBuilder().addComponents(nameInput), new ARBuilder().addComponents(typeInput), new ARBuilder().addComponents(patternInput), new ARBuilder().addComponents(actionInput));
        await interaction.showModal(modal);
        return;
      } else if (modalAction === 'modal_edit') {
        // customId: automod:modal_edit:guildId:triggerId
        const triggerId = parts[3];
        const name = interaction.fields.getTextInputValue('name');
        const trigger_type = interaction.fields.getTextInputValue('type');
        const pattern = interaction.fields.getTextInputValue('pattern');
        const actionVal = interaction.fields.getTextInputValue('action');
        const updated = editTrigger(guildId, triggerId, { name, trigger_type, pattern, action: actionVal });
        if (updated) await interaction.reply({ content: 'Trigger updated successfully.', ephemeral: true });
        else await interaction.reply({ content: 'Failed to update trigger (id not found).', ephemeral: true });
        return;
      } else if (modalAction === 'modal_remove') {
        const id = interaction.fields.getTextInputValue('trigger_id');
        const removed = removeTrigger(guildId, id);
        if (removed > 0) await interaction.reply({ content: `Removed ${removed} trigger(s).`, ephemeral: true });
        else await interaction.reply({ content: `No trigger removed. ID not found.`, ephemeral: true });
        return;
      } else if (modalAction === 'modal_ai_edit') {
        const json = interaction.fields.getTextInputValue('ai_json');
        try {
          const parsed = JSON.parse(json);
          const cfg = getGuildConfig(guildId);
          cfg.perspectiveThresholds = parsed;
          setGuildConfig(guildId, cfg);
          await interaction.reply({ content: 'AI thresholds updated.', ephemeral: true });
        } catch (e) {
          await interaction.reply({ content: 'Failed to parse JSON: ' + e.message, ephemeral: true });
        }
        return;
      } else if (modalAction === 'modal_ai_test') {
        const sample = interaction.fields.getTextInputValue('sample_text');
        const scores = await analyzeTextPerspective(sample);
        if (!scores) {
          await interaction.reply({ content: 'Perspective analysis failed or not configured.', ephemeral: true });
        } else {
          await interaction.reply({ content: `Perspective results:\n${Object.entries(scores).map(([k,v]) => `${k}: ${v.toFixed(3)}`).join('\n')}`, ephemeral: true });
        }
        return;
      }
    }

  } catch (e) {
    console.warn('handleInteraction error', e && e.stack);
    try {
      if (!interaction.replied) await interaction.reply({ content: 'Internal error: ' + (e && e.message), ephemeral: true });
    } catch (ex) {}
  }
}

// ----------------------------- MESSAGE PIPELINE (main detection flow) -----------------------------
/**
 * Steps:
 *  1. Quick guards: ignore bots and DMs.
 *  2. Load guild cfg
 *  3. Trusted roles / moderator exempt
 *  4. Banned words -> delete+warn
 *  5. DB triggers -> execute configured action
 *  6. Spam detection -> escalate
 *  7. Link protection: whitelist/blacklist
 *  8. Image scanning (Vision) -> per-category action if thresholds hit
 *  9. Perspective (text) -> per-category action if thresholds hit
 *  10. Language enforcement (optional)
 *  11. Fallback: none
 *
 * The pipeline returns an object describing any action taken.
 */

async function processMessage(client, message) {
  try {
    if (!message.guild || message.author.bot) return { actioned: false };
    const guildId = message.guild.id;
    const cfg = getGuildConfig(guildId);

    // early exit if trusted
    const member = message.member;
    let isTrusted = false;
    try {
      if (message.guild.ownerId === member?.id) isTrusted = true;
      if (member && member.permissions.has(PermissionsBitField.Flags.Administrator)) isTrusted = true;
      if (member && member.roles.cache && (cfg.trustedRoleIds || []).some(id => member.roles.cache.has(id))) isTrusted = true;
    } catch (e) {}

    if (isTrusted) return { actioned: false };

    const content = message.content || '';

    // 1) banned words (substring)
    for (const bad of (cfg.bannedWords || [])) {
      if (!bad) continue;
      if (content.toLowerCase().includes(bad.toLowerCase())) {
        const reason = `banned_word:${bad}`;
        await performAction(client, guildId, message.author.id, 'delete+warn', { messageObj: message, reason, category: 'banned_word' });
        // escalate counters (spam logic or infractions may use maybeEscalate)
        return { actioned: true, reason, category: 'banned_word' };
      }
    }

    // 2) DB triggers
    const matchedTrigger = testTriggers(guildId, content);
    if (matchedTrigger) {
      const reason = `trigger:${matchedTrigger.id}`;
      await performAction(client, guildId, message.author.id, matchedTrigger.action, { messageObj: message, reason, category: 'trigger', trigger: matchedTrigger });
      return { actioned: true, reason, category: 'trigger', trigger: matchedTrigger };
    }

    // 3) Spam detection
    const spamRec = recordMessageForSpam(guildId, message.author.id);
    const spamAction = determineSpamAction(guildId, spamRec.count);
    if (spamAction) {
      // base action: delete+warn, but we also record counters
      await performAction(client, guildId, message.author.id, spamAction.action, { messageObj: message, reason: spamAction.reason, category: 'spam' });
      // optionally clear spam timestamps after action to avoid repeated triggers
      clearSpamForUser(guildId, message.author.id);
      return { actioned: true, reason: spamAction.reason, category: 'spam' };
    }

    // 4) link protection
    const domains = extractDomains(content);
    if (domains.length) {
      for (const d of domains) {
        if (domainMatches(d, cfg.linksBlacklist || [])) {
          const reason = `link_blacklist:${d}`;
          await performAction(client, guildId, message.author.id, 'delete+warn', { messageObj: message, reason, category: 'link' });
          return { actioned: true, reason, category: 'link' };
        }
      }
      if ((cfg.linksWhitelist || []).length > 0) {
        // ensure at least one domain in whitelist
        const allowed = domains.some(dom => domainMatches(dom, cfg.linksWhitelist || []));
        if (!allowed) {
          const reason = `link_not_whitelisted:${domains[0]}`;
          await performAction(client, guildId, message.author.id, 'delete+warn', { messageObj: message, reason, category: 'link' });
          return { actioned: true, reason, category: 'link' };
        }
      }
    }

    // 5) image scanning (Vision)
    if (cfg.nsfwScanEnabled && message.attachments && message.attachments.size > 0) {
      for (const att of message.attachments.values()) {
        // fetch small images only; avoid huge attachments (we'll skip > 2MB for safety)
        if (att.size && att.size > 4 * 1024 * 1024) continue; // skip >4MB to avoid heavy usage
        const b64 = await fetchUrlToBase64(att.url).catch(() => null);
        if (!b64) continue;
        const sha = sha1Base64(b64);
        const cached = getVisionCache(sha);
        let vs = cached;
        if (!vs) {
          vs = await analyzeImageSafeSearch(b64);
        }
        if (vs) {
          // check categories
          const vth = cfg.visionThresholds || {};
          for (const cat of ['adult','violence','racy']) {
            const val = vs[cat];
            if (!val) continue;
            const entry = vth[cat];
            if (entry && (entry.levels || []).includes(val)) {
              // matched
              const reason = `vision_${cat}:${val}`;
              await performAction(client, guildId, message.author.id, entry.action || 'delete+warn', { messageObj: message, reason, category: 'vision', vision: vs });
              return { actioned: true, reason, category: 'vision', detail: vs };
            }
          }
        }
      }
    }

    // 6) Perspective (text moderation)
    if (PERSPECTIVE_KEY && content && content.length > 4) {
      const scores = await analyzeTextPerspective(content);
      if (scores) {
        const pth = cfg.perspectiveThresholds || DEFAULT_GUILD_CFG.perspectiveThresholds;
        for (const [cat, entry] of Object.entries(pth)) {
          const score = scores[cat];
          if (score != null && score >= (entry.threshold || 0.85)) {
            const reason = `perspective_${cat}:${score.toFixed(3)}`;
            await performAction(client, guildId, message.author.id, entry.action || 'delete+warn', { messageObj: message, reason, category: 'perspective', scores });
            return { actioned: true, reason, category: 'perspective', scores };
          }
        }
      }
    }

    // 7) Language enforcement (optional) - skip unless specific per-channel config added
    // Future: implement per-channel language settings in DB

    return { actioned: false };
  } catch (e) {
    console.warn('processMessage error', e && e.stack);
    return { actioned: false, error: e && e.message };
  }
}

// ----------------------------- MICRO-SERVICE JSON-RPC (stdin/stdout) -----------------------------
/**
 * If launched without BOT_TOKEN, automod.js runs in microservice mode:
 * - listens for newline-delimited JSON on stdin
 * - supports commands:
 *    { id, cmd: 'health' }
 *    { id, cmd: 'scan_message', data: { guild_id, channel_id, author_id, content, attachments: [{url,name}] } }
 *    { id, cmd: 'get_config', data: { guild_id } }
 *    { id, cmd: 'sync_preview', data: { guild_id } }
 *    { id, cmd: 'sync_execute', data: { guild_id } }  // executes sync — requires BOT_TOKEN & client
 *
 * Responses are newline-delimited JSON objects with same id:
 *  { id, ok: true, result: ... } or { id, ok: false, error: '...' }
 */

function sendJsonToStdout(obj) {
  try {
    process.stdout.write(JSON.stringify(obj) + '\n');
  } catch (e) {}
}

async function handleRpcMessage(msg, client) {
  const id = msg.id || null;
  try {
    if (msg.cmd === 'health') {
      sendJsonToStdout({ id, ok: true, result: { status: 'ok', pid: process.pid } });
      return;
    } else if (msg.cmd === 'scan_message') {
      const data = msg.data || {};
      const res = await scanMessageForRPC(client, data);
      sendJsonToStdout({ id, ok: true, result: res });
      return;
    } else if (msg.cmd === 'get_config') {
      const gid = msg.data && msg.data.guild_id;
      if (!gid) { sendJsonToStdout({ id, ok: false, error: 'guild_id required' }); return; }
      const cfg = getGuildConfig(gid);
      sendJsonToStdout({ id, ok: true, result: cfg });
      return;
    } else if (msg.cmd === 'sync_preview') {
      const gid = msg.data && msg.data.guild_id;
      if (!gid) { sendJsonToStdout({ id, ok: false, error: 'guild_id required' }); return; }
      if (!client) { sendJsonToStdout({ id, ok: false, error: 'client required for sync preview' }); return; }
      try {
        const preview = await syncFallbackToNativeAutoModPreview(client, gid);
        sendJsonToStdout({ id, ok: true, result: preview });
      } catch (e) { sendJsonToStdout({ id, ok: false, error: e && e.message }); }
      return;
    } else if (msg.cmd === 'sync_execute') {
      const gid = msg.data && msg.data.guild_id;
      if (!gid) { sendJsonToStdout({ id, ok: false, error: 'guild_id required' }); return; }
      if (!client) { sendJsonToStdout({ id, ok: false, error: 'client required for sync execute' }); return; }
      try {
        const preview = await syncFallbackToNativeAutoModPreview(client, gid);
        const result = await executeSyncToNativeAutoMod(client, gid, preview);
        sendJsonToStdout({ id, ok: true, result });
      } catch (e) { sendJsonToStdout({ id, ok: false, error: e && e.message }); }
      return;
    } else {
      sendJsonToStdout({ id, ok: false, error: 'unknown_cmd' });
      return;
    }
  } catch (e) {
    sendJsonToStdout({ id, ok: false, error: e && e.message });
  }
}

// For RPC scanning, we call the same internal pipeline but with messageObj = null
async function scanMessageForRPC(client, data) {
  const info = {
    guildId: data.guild_id,
    channelId: data.channel_id,
    authorId: data.author_id,
    content: data.content,
    attachments: data.attachments || [] // each {url,name}
  };
  // We'll emulate a messageObj with only minimal data where needed; pass client
  const res = await scanMessage({ client, ...info });
  return res;
}

// Expose a simpler scanMessage wrapper for RPC and programmatic use
async function scanMessage({ client = null, guildId, channelId, authorId, content = '', attachments = [], messageObj = null }) {
  // This wrapper will call processMessage but with messageObj prepared if available
  // Create a minimal message-like object if none provided for processMessage
  const fakeMessage = messageObj || {
    guild: { id: guildId },
    author: { id: authorId },
    content,
    attachments: {
      size: attachments.length,
      values: () => attachments.map(a => ({ url: a.url, size: a.size || 0, name: a.name || '' }))
    },
    member: null,
    channel: { id: channelId }
  };
  // If client is present and guildId available, we can fetch member to populate member for exemptions
  if (client && client.guilds && fakeMessage && fakeMessage.author && typeof fakeMessage.author.id === 'string') {
    try {
      const g = await client.guilds.fetch(guildId).catch(() => null);
      if (g) {
        fakeMessage.guild = g;
        const m = await g.members.fetch(authorId).catch(() => null);
        if (m) fakeMessage.member = m;
        // channel resolution for messageObj is expensive; skip if no channelId
        if (channelId) {
          const ch = await g.channels.fetch(channelId).catch(() => null);
          if (ch) fakeMessage.channel = ch;
        }
      }
    } catch (e) {}
  }
  return await processMessage(client, fakeMessage);
}

// ----------------------------- DISCORD CLIENT STARTUP -----------------------------
/**
 * startClient() will:
 *  - instantiate a discord.js Client (if BOT_TOKEN provided)
 *  - register slash command globally (or per-guild if desired)
 *  - attach listeners: messageCreate, interactionCreate
 *  - start a small unmute watcher to unsilence expired mutes (applies to role-based mutes persisted in config)
 */
let clientInstance = null;
let unmuteInterval = null;

async function startClient() {
  if (!BOT_TOKEN) return null;
  if (clientInstance) return clientInstance;
  const client = new Client({ intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages, GatewayIntentBits.MessageContent, GatewayIntentBits.GuildMembers], partials: [Partials.Channel, Partials.GuildMember] });

  client.on('ready', async () => {
    console.log(`AutoMod Neo client ready as ${client.user.tag}`);
    // register slash command
    try {
      const rest = new REST({ version: '10' }).setToken(BOT_TOKEN);
      const appId = client.user.id;
      const cmd = buildAutomodCommand().toJSON();
      // For faster dev iteration, we could register per-guild. For production, global is OK but slower to update.
      await rest.put(Routes.applicationCommands(appId), { body: [cmd] });
      console.log('Registered /automod dashboard command globally.');
    } catch (e) { console.warn('Failed to register slash commands', e && e.message); }

    // unmute watcher: every 20s check temp mutes and unmute expired
    if (!unmuteInterval) {
      unmuteInterval = setInterval(async () => {
        try {
          // iterate guild configs
          const rows = db.prepare('SELECT guild_id, config_json FROM guilds').all();
          for (const row of rows) {
            const gid = row.guild_id;
            const cfg = tryParse(row.config_json) || {};
            const tms = cfg.tempMutes || [];
            let changed = false;
            for (const tm of [...tms]) {
              if (!tm.unmuteAt) continue;
              const unmuteAt = new Date(tm.unmuteAt);
              if (isNaN(unmuteAt.getTime())) continue;
              if (unmuteAt <= new Date()) {
                // try to unmute the user: remove mute role
                try {
                  const g = await client.guilds.fetch(gid).catch(() => null);
                  if (g && cfg.muteRoleId) {
                    const member = await g.members.fetch(tm.userId).catch(() => null);
                    if (member) {
                      await member.roles.remove(cfg.muteRoleId, 'AutoMod unmute (expired)').catch(() => {});
                    }
                  }
                } catch (e) {}
                // remove from tempMutes
                const idx = tms.indexOf(tm);
                if (idx >= 0) tms.splice(idx, 1);
                changed = true;
              }
            }
            if (changed) {
              cfg.tempMutes = tms;
              setGuildConfig(gid, cfg);
            }
          }
        } catch (e) {
          console.warn('unmuteInterval error', e && e.message);
        }
      }, 20*1000);
    }
  });

  // messageCreate: pipeline
  client.on('messageCreate', async (message) => {
    try {
      const res = await processMessage(client, message);
      // if actioned, we might log more verbose info
      if (res && res.actioned) {
        // send a compact mod log (if not already)
        const embed = buildEmbed({
          title: 'AutoMod — Action taken',
          description: `Action: ${res.reason || 'actioned'}`,
          fields: [ { name: 'User', value: `<@${message.author.id}>` }, { name: 'Category', value: res.category || 'unknown' } ],
          color: COLORS.warning
        });
        await sendToGuildLog(client, message.guild.id, embed, message.author.id);
      }
    } catch (e) {
      console.warn('messageCreate pipeline error', e && e.stack);
    }
  });

  // interactionCreate: full handler
  client.on('interactionCreate', async (interaction) => {
    try {
      await handleInteraction(interaction, client);
    } catch (e) {
      console.warn('interactionCreate handler error', e && e.stack);
    }
  });

  // start login
  await client.login(BOT_TOKEN);
  clientInstance = client;
  return client;
}

// ----------------------------- EXPORTS & LAUNCH -----------------------------
/**
 * Exports:
 *  - startClient   : starts discord client if BOT_TOKEN set
 *  - scanMessage   : programmatic API to scan a message (same as RPC)
 *  - getGuildConfig, setGuildConfig, addTrigger, editTrigger, removeTrigger, listTriggers
 *
 * If run as main, we start client if BOT_TOKEN present, and always start RPC stdin listener.
 */

async function main() {
  // start client if token provided
  let client = null;
  if (BOT_TOKEN) {
    try { client = await startClient(); } catch (e) { console.warn('Failed to start client:', e && e.message); }
  } else {
    console.log('No BOT_TOKEN provided — running in microservice mode (no discord client).');
  }

  // stdin JSON-RPC loop
  process.stdin.setEncoding('utf8');
  let buffer = '';
  process.stdin.on('data', chunk => {
    buffer += chunk;
    let idx;
    while ((idx = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 1);
      if (!line) continue;
      let msg = null;
      try { msg = JSON.parse(line); } catch (e) { sendJsonToStdout({ id: null, ok: false, error: 'invalid_json' }); continue; }
      handleRpcMessage(msg, client).catch(e => sendJsonToStdout({ id: msg.id || null, ok: false, error: e && e.message }));
    }
  });
}

// Node entrypoint
if (require.main === module) {
  main().catch(e => console.error('AutoMod main failed', e && e.stack));
}

// module exports for programmatic integration
module.exports = {
  startClient,
  scanMessage: scanMessageForRPC, // re-export simpler signature
  getGuildConfig,
  setGuildConfig,
  addTrigger,
  editTrigger,
  removeTrigger,
  listTriggers,
  analyzeTextPerspective,
  analyzeImageSafeSearch
};
