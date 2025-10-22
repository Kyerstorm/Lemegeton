/**
 * automod.js
 *
 * Usage modes:
 * 1) Standalone Node process (recommended): run this with NODE to operate the AutoMod as its own bot.
 *    - Requires BOT_TOKEN env
 *    - Exposes full Discord UI (slash commands, dashboard)
 *
 * 2) Microservice mode (for Python main bot):
 *    - Start this process with NODE (with BOT_TOKEN or without)
 *    - Python can spawn it and communicate via stdin/stdout JSON messages:
 *        -> send JSON {"id":"uuid","cmd":"scan_message","data":{guild_id,channel_id,author_id,content,attachments:[{url,name}]}}
 *        <- receive JSON {"id":"uuid","ok":true,"result":{...}} or {"id":"uuid","ok":false,"error":"..."}
 *    - Also supports "health" and "reload_config" commands.
 *
 * Required env variables:
 * - BOT_TOKEN (only if you want this process to operate as the Discord bot)
 * - PERSPECTIVE_KEY (optional, for text moderation)
 * - GOOGLE_VISION_KEY (optional, for image safe-search)
 * 
 * Notes:
 * - The file intentionally supports both direct discord.js client and microservice IPC.
 * - Make sure the bot running this file has MANAGE_GUILD, MANAGE_ROLES, MODERATE_MEMBERS, and application.commands.
 */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const fetch = require('node-fetch');
const Database = require('better-sqlite3');
const { REST } = require('@discordjs/rest');
const { Routes } = require('discord-api-types/v10');
const { SlashCommandBuilder, ModalBuilder, TextInputBuilder, TextInputStyle, ActionRowBuilder } = require('@discordjs/builders');
const { Client, GatewayIntentBits, Partials, EmbedBuilder, ActionRowBuilder: ARB, ButtonBuilder, ButtonStyle, PermissionsBitField, SelectMenuBuilder, StringSelectMenuBuilder, ModalSubmitInteraction } = require('discord.js');

const BOT_TOKEN = process.env.BOT_TOKEN || null;
const PERSPECTIVE_KEY = process.env.PERSPECTIVE_KEY || null;
const GOOGLE_VISION_KEY = process.env.GOOGLE_VISION_KEY || null;
const DB_PATH = process.env.SQLITE_DB_PATH || path.join(process.cwd(), 'automod_neo.db');
const VISION_CACHE_TTL_MS = 24 * 3600 * 1000; // 24h

// Neo-dark palette
const COLORS = { bg: 0x0d1117, accent: 0x00e6ff, danger: 0xff4d8f, warn: 0xffb86b, info: 0x8be9fd, success: 0x50fa7b };

// init db
let db;
function initDb() {
  if (db) return;
  try {
    db = new Database(DB_PATH);
    db.pragma('journal_mode = WAL');
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
  } catch (e) {
    console.error('DB init failed', e);
    process.exit(1);
  }
}

initDb();

// default config
const DEFAULT_CFG = {
  logChannelId: null,
  modRoleIds: [],
  trustedRoleIds: [],
  bannedWords: [],
  automodTriggers: [],
  spamThreshold: { messages: 5, seconds: 8 },
  linksWhitelist: [],
  linksBlacklist: [],
  nsfwScanEnabled: true,
  muteRoleId: null,
  perspectiveThresholds: { TOXICITY: { threshold: 0.85, action: 'delete+warn' }, INSULT: { threshold: 0.85, action: 'delete+warn' } },
  visionThresholds: { adult: { levels: ['LIKELY','VERY_LIKELY'], action: 'delete+warn' }, violence: { levels: ['LIKELY','VERY_LIKELY'], action: 'delete+warn' } },
  automodSync: false
};

function getCfg(guildId) {
  const row = db.prepare('SELECT config_json FROM guilds WHERE guild_id = ?').get(guildId);
  if (!row) {
    const cfg = JSON.stringify(DEFAULT_CFG);
    db.prepare('INSERT OR REPLACE INTO guilds (guild_id, config_json) VALUES (?, ?)').run(guildId, cfg);
    return JSON.parse(cfg);
  } else {
    try { return JSON.parse(row.config_json); } catch (e) { return JSON.parse(JSON.stringify(DEFAULT_CFG)); }
  }
}
function setCfg(guildId, cfg) {
  db.prepare('INSERT OR REPLACE INTO guilds (guild_id, config_json) VALUES (?, ?)').run(guildId, JSON.stringify(cfg));
}

function addInfraction(guildId, userId, moderatorId, action, reason, meta = {}) {
  db.prepare('INSERT INTO infractions (guild_id,user_id,moderator_id,action,reason,meta_json) VALUES (?,?,?,?,?,?)')
    .run(guildId, userId, moderatorId, action, reason, JSON.stringify(meta));
}

// simple SHA1
function sha1(input) { return crypto.createHash('sha1').update(input).digest('hex'); }

// ---------------- Exponential backoff helper ----------------
async function sleep(ms) { return new Promise(res => setTimeout(res, ms)); }
async function withRetries(fn, opts = {}) {
  const attempts = opts.attempts || 3;
  const baseMs = opts.baseMs || 400;
  let attempt = 0;
  while (attempt < attempts) {
    try {
      return await fn(attempt);
    } catch (err) {
      attempt++;
      const status = err && err.status;
      if (attempt >= attempts) throw err;
      // exponential + jitter
      let backoff = baseMs * Math.pow(2, attempt) + Math.round(Math.random() * baseMs);
      // if 429, more backoff
      if (status === 429) backoff *= 2;
      await sleep(backoff);
    }
  }
  throw new Error('Retries exhausted');
}

// ---------------- Perspective API (text) ----------------
async function analyzeTextPerspective(text) {
  if (!PERSPECTIVE_KEY) return null;
  const url = `https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze?key=${PERSPECTIVE_KEY}`;
  const payload = {
    comment: { text },
    languages: ['en'],
    requestedAttributes: { TOXICITY: {}, SEVERE_TOXICITY: {}, INSULT: {}, IDENTITY_ATTACK: {}, THREAT: {}, SEXUALLY_EXPLICIT: {} }
  };
  return await withRetries(async () => {
    const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    if (!res.ok) {
      const txt = await res.text().catch(() => '');
      const e = new Error('Perspective API error: ' + res.status);
      e.status = res.status;
      e.text = txt;
      throw e;
    }
    const json = await res.json();
    const out = {};
    const attrs = (json.attributeScores || {});
    for (const k of Object.keys(attrs)) {
      out[k] = (attrs[k] && attrs[k].summaryScore && attrs[k].summaryScore.value) || 0.0;
    }
    return out;
  }, { attempts: 4, baseMs: 500 });
}

// ---------------- Google Vision SafeSearch (with cache) ----------------
function getVisionCache(sha) {
  const row = db.prepare('SELECT response_json,created_at FROM vision_cache WHERE sha1 = ?').get(sha);
  if (!row) return null;
  if (Date.now() - row.created_at > VISION_CACHE_TTL_MS) {
    db.prepare('DELETE FROM vision_cache WHERE sha1 = ?').run(sha);
    return null;
  }
  try { return JSON.parse(row.response_json); } catch (e) { return null; }
}
function setVisionCache(sha, resp) {
  db.prepare('INSERT OR REPLACE INTO vision_cache (sha1,response_json,created_at) VALUES (?,?,?)').run(sha, JSON.stringify(resp), Date.now());
}

async function callVisionBase64(base64) {
  if (!GOOGLE_VISION_KEY) return null;
  const url = `https://vision.googleapis.com/v1/images:annotate?key=${GOOGLE_VISION_KEY}`;
  const payload = { requests: [{ image: { content: base64 }, features: [{ type: 'SAFE_SEARCH_DETECTION' }] }] };
  return await withRetries(async () => {
    const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    if (!res.ok) {
      const txt = await res.text().catch(() => '');
      const e = new Error('Vision API error: ' + res.status);
      e.status = res.status;
      e.text = txt;
      throw e;
    }
    const json = await res.json();
    const resp = (json.responses && json.responses[0] && json.responses[0].safeSearchAnnotation) || null;
    if (resp) setVisionCache(sha1(base64), resp);
    return resp;
  }, { attempts: 4, baseMs: 600 });
}

async function fetchUrlAsBase64(url) {
  try {
    const r = await fetch(url);
    if (!r.ok) return null;
    const b = await r.arrayBuffer();
    return Buffer.from(b).toString('base64');
  } catch (e) { return null; }
}

// ---------------- Discord embed / logging helpers ----------------
function neoEmbed(title, desc, fields = [], color = COLORS.bg) {
  const e = new EmbedBuilder().setTitle(title).setDescription(desc).setColor(color).setTimestamp();
  fields.forEach(f => e.addFields([{ name: f.name, value: f.value, inline: !!f.inline }]));
  // subtle footer
  e.setFooter({ text: 'AutoMod • Neo', iconURL: null });
  return e;
}

async function sendGuildLog(client, guildId, embed, targetUserId = null) {
  try {
    const cfg = getCfg(guildId);
    if (!cfg.logChannelId) return;
    const g = await client.guilds.fetch(guildId).catch(() => null);
    if (!g) return;
    const ch = await g.channels.fetch(cfg.logChannelId).catch(() => null);
    if (!ch || !ch.isTextBased()) return;
    const row = new ARB().addComponents(
      new ButtonBuilder().setCustomId(`mod:warn:${guildId}:${targetUserId || '0'}`).setLabel('Warn').setStyle(ButtonStyle.Primary),
      new ButtonBuilder().setCustomId(`mod:mute:${guildId}:${targetUserId || '0'}`).setLabel('Temp Mute').setStyle(ButtonStyle.Secondary),
      new ButtonBuilder().setCustomId(`mod:delete:${guildId}:${targetUserId || '0'}`).setLabel('Delete Msg').setStyle(ButtonStyle.Danger),
      new ButtonBuilder().setCustomId(`mod:kick:${guildId}:${targetUserId || '0'}`).setLabel('Kick').setStyle(ButtonStyle.Danger),
      new ButtonBuilder().setCustomId(`mod:ban:${guildId}:${targetUserId || '0'}`).setLabel('Ban').setStyle(ButtonStyle.Danger),
    );
    await ch.send({ embeds: [embed], components: [row] }).catch(() => {});
  } catch (e) {
    console.error('sendGuildLog error', e);
  }
}

// ---------------- Message pipeline (scanning) ----------------
async function executeAction(client, guild, messageOrMeta, actionStr, reason = 'automod') {
  // actionStr: "delete+warn" or "temp_mute:300+warn"
  const parts = actionStr.split('+').map(s => s.trim());
  const meta = messageOrMeta.meta || {};
  const guildId = typeof guild === 'string' ? guild : guild.id;
  const userId = messageOrMeta.authorId || messageOrMeta.userId || (messageOrMeta.author && messageOrMeta.author.id) || null;

  for (const p of parts) {
    if (p.startsWith('temp_mute')) {
      const sec = (p.includes(':') ? parseInt(p.split(':')[1]) || 300 : 300);
      // If we have discord client & guild object, try to apply mute role or timeout
      if (client && typeof client === 'object' && client.guilds) {
        try {
          const g = await client.guilds.fetch(guildId);
          const m = await g.members.fetch(userId).catch(() => null);
          if (m) {
            // try timeout (discord v14)
            try { await m.timeout(sec * 1000, `AutoMod: ${reason}`); } catch (e) {
              // fallback to adding mute role
              const cfg = getCfg(guildId);
              let muteRole = cfg.muteRoleId ? await g.roles.fetch(cfg.muteRoleId).catch(() => null) : null;
              if (!muteRole) {
                muteRole = await g.roles.create({ name: 'Muted', reason: 'AutoMod created mute role' }).catch(() => null);
                if (muteRole) { const cfg2 = getCfg(guildId); cfg2.muteRoleId = muteRole.id; setCfg(guildId, cfg2); }
              }
              if (muteRole) await m.roles.add(muteRole, `AutoMod temp mute: ${reason}`).catch(() => {});
            }
          }
        } catch (e) { /* best-effort */ }
      }
      addInfraction(guildId, userId, null, 'temp_mute', reason, meta);
    } else if (p === 'delete') {
      // If message object provided, try to delete it.
      if (messageOrMeta.messageObj && messageOrMeta.messageObj.delete) {
        try { await messageOrMeta.messageObj.delete().catch(() => {}); } catch (e) {}
      }
      addInfraction(guildId, userId, null, 'delete', reason, meta);
      if (client) await sendGuildLog(client, guildId, neoEmbed('Message deleted by AutoMod', `User <@${userId}>\nReason: ${reason}`, [{ name: 'Action', value: 'delete', inline: true }], COLORS.warn), userId);
    } else if (p === 'warn') {
      // DM
      if (client && messageOrMeta && messageOrMeta.authorId) {
        try {
          const g = await client.guilds.fetch(guildId).catch(() => null);
          if (g) {
            const member = await g.members.fetch(userId).catch(() => null);
            if (member) {
              await member.send({ embeds: [neoEmbed('You received a warning', `In **${g.name}**\nReason: ${reason}`)] }).catch(() => {});
            }
          }
        } catch (e) {}
      }
      addInfraction(guildId, userId, null, 'warn', reason, meta);
      if (client) await sendGuildLog(client, guildId, neoEmbed('User warned by AutoMod', `User <@${userId}>\nReason: ${reason}`, [], COLORS.info), userId);
    } else if (p === 'kick') {
      if (client) {
        try {
          const g = await client.guilds.fetch(guildId);
          await g.members.kick(userId, `AutoMod: ${reason}`).catch(() => {});
          addInfraction(guildId, userId, null, 'kick', reason, meta);
          await sendGuildLog(client, guildId, neoEmbed('User kicked by AutoMod', `<@${userId}>`, [], COLORS.danger), userId);
        } catch (e) {}
      }
    } else if (p === 'ban') {
      if (client) {
        try {
          const g = await client.guilds.fetch(guildId);
          await g.bans.create(userId, { reason: `AutoMod: ${reason}` }).catch(() => {});
          addInfraction(guildId, userId, null, 'ban', reason, meta);
          await sendGuildLog(client, guildId, neoEmbed('User banned by AutoMod', `<@${userId}>`, [], COLORS.danger), userId);
        } catch (e) {}
      }
    } else {
      // unknown action: ignore
    }
  }
}

// Main scanner: returns summary and optionally performs actions if client is provided
async function scanMessage({ client = null, guildId, channelId, authorId, content = '', attachments = [], messageObj = null }) {
  // quick guard
  const cfg = getCfg(guildId);
  // check trusted roles — skipped: requires member fetch (expensive) when running as microservice
  // 1) banned words
  const lowered = (content || '').toLowerCase();
  for (const bad of (cfg.bannedWords || [])) {
    if (!bad) continue;
    if (lowered.includes(bad.toLowerCase())) {
      const reason = `banned_word:${bad}`;
      await executeAction(client, guildId, { authorId, messageObj, meta: { reason } }, 'delete+warn', reason);
      return { actioned: true, reason, matched: bad, category: 'banned_word' };
    }
  }

  // 2) links blacklist/whitelist
  const urlRegex = /https?:\/\/[^\s/$.?#].[^\s]*/gi;
  const found = (content.match(urlRegex) || []).map(u => {
    try { return new URL(u).hostname; } catch (e) { return null; }
  }).filter(Boolean);
  if (found.length) {
    for (const d of found) {
      for (const p of (cfg.linksBlacklist || [])) if (d.includes(p)) {
        const reason = `link_blacklisted:${d}`;
        await executeAction(client, guildId, { authorId, messageObj, meta: { reason } }, 'delete+warn', reason);
        return { actioned: true, reason, matched: d, category: 'link' };
      }
    }
    if ((cfg.linksWhitelist || []).length > 0) {
      const allowed = found.some(dom => (cfg.linksWhitelist || []).some(p => dom.includes(p)));
      if (!allowed) {
        const reason = `link_not_whitelisted:${found[0]}`;
        await executeAction(client, guildId, { authorId, messageObj, meta: { reason } }, 'delete+warn', reason);
        return { actioned: true, reason, matched: found[0], category: 'link' };
      }
    }
  }

  // 3) attachments: vision check
  if (cfg.nsfwScanEnabled && attachments && attachments.length) {
    for (const a of attachments) {
      const base64 = await fetchUrlAsBase64(a.url);
      const sha = base64 ? sha1(base64) : null;
      let cached = sha ? getVisionCache(sha) : null;
      let visionResp = null;
      if (cached) visionResp = cached;
      else if (base64) visionResp = await callVisionBase64(base64).catch(() => null);
      if (!visionResp) {
        // skip if no vision
      } else {
        // check thresholds
        const vth = cfg.visionThresholds || {};
        for (const cat of ['adult','violence','racy']) {
          const val = visionResp[cat];
          if (!val) continue;
          const entry = vth[cat];
          if (entry && entry.levels && entry.levels.includes(val)) {
            const reason = `vision_${cat}:${val}`;
            await executeAction(client, guildId, { authorId, messageObj, meta: { reason, vision: visionResp } }, entry.action || 'delete+warn', reason);
            return { actioned: true, reason, matched: cat, category: 'vision', detail: visionResp };
          }
        }
      }
    }
  }

  // 4) Perspective (text)
  if (PERSPECTIVE_KEY && content && content.length > 3) {
    try {
      const scores = await analyzeTextPerspective(content);
      if (scores) {
        const pth = cfg.perspectiveThresholds || {};
        for (const [cat, cfgEntry] of Object.entries(pth)) {
          const score = scores[cat];
          if (score != null && score >= (cfgEntry.threshold || 0.85)) {
            const reason = `perspective_${cat}:${score.toFixed(3)}`;
            await executeAction(client, guildId, { authorId, messageObj, meta: { reason, scores } }, cfgEntry.action || 'delete+warn', reason);
            return { actioned: true, reason, matched: cat, category: 'perspective', scores };
          }
        }
      }
    } catch (e) {
      // gracefully continue if perspective fails
      console.warn('Perspective error', e && e.message);
    }
  }

  // 5) spam detection is intentionally left to the main bot (maintain per-guild caches) — but we can optionally implement simple counters here later.
  return { actioned: false, reason: null };
}

// ---------------- Discord UI: dashboard command ----------------
function buildDashboardCommand() {
  return new SlashCommandBuilder()
    .setName('automod')
    .setDescription('AutoMod Neo dashboard & management')
    .addSubcommand(s => s.setName('dashboard').setDescription('Open the interactive AutoMod Dashboard'));
}

// Minimal UI helpers for neo-dark aesthetic
function makeDashboardEmbed(guildId) {
  const cfg = getCfg(guildId);
  const fields = [
    { name: 'Log Channel', value: cfg.logChannelId ? `<#${cfg.logChannelId}>` : 'Not set', inline: true },
    { name: 'Mod roles', value: (cfg.modRoleIds||[]).map(r=>`<@&${r}>`).join(', ') || 'None', inline: true },
    { name: 'Trusted roles', value: (cfg.trustedRoleIds||[]).map(r=>`<@&${r}>`).join(', ') || 'None', inline: true },
    { name: 'Banned words', value: (cfg.bannedWords || []).slice(0,10).join(', ') || 'None', inline: false },
  ];
  return neoEmbed('AutoMod • Dashboard', 'Neo-dark control panel — select a section below', fields, COLORS.bg);
}

function dashboardActionRow(guildId) {
  const menu = new StringSelectMenuBuilder()
    .setCustomId(`automod:menu:${guildId}`)
    .setPlaceholder('Select section')
    .addOptions(
      { label: 'Configuration', value: 'config', description: 'View and edit general settings', emoji: '⚙️' },
      { label: 'Rules & Triggers', value: 'triggers', description: 'View/add/remove fallback triggers', emoji: '⚠️' },
      { label: 'AI Thresholds', value: 'ai', description: 'Adjust Perspective & Vision thresholds', emoji: '🧠' },
      { label: 'Infractions / Logs', value: 'logs', description: 'Inspect infractions and take action', emoji: '📊' },
      { label: 'AutoMod Sync', value: 'sync', description: 'View native Discord AutoMod rules and sync', emoji: '🔁' },
    );
  return new ARB().addComponents(menu);
}

// ---------------- Node process: optional discord client ----------------
let client = null;
async function startDiscordClient() {
  if (!BOT_TOKEN) return null;
  const c = new Client({ intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages, GatewayIntentBits.MessageContent, GatewayIntentBits.GuildMembers], partials: [Partials.Channel] });
  c.once('ready', async () => {
    console.log(`AutoMod Neo client ready — ${c.user.tag}`);
    // register slash command
    try {
      const rest = new REST({ version: '10' }).setToken(BOT_TOKEN);
      await rest.put(Routes.applicationCommands(c.user.id), { body: [buildDashboardCommand().toJSON()] });
      console.log('Registered automod dashboard command globally.');
    } catch (e) { console.warn('Slash registration failed', e && e.message); }
  });

  c.on('interactionCreate', async (interaction) => {
    try {
      if (interaction.isChatInputCommand() && interaction.commandName === 'automod' && interaction.options.getSubcommand() === 'dashboard') {
        await interaction.deferReply({ ephemeral: true });
        const guildId = interaction.guildId;
        const embed = makeDashboardEmbed(guildId);
        const row = dashboardActionRow(guildId);
        await interaction.editReply({ embeds: [embed], components: [row] });

        // Listen for the select menu selection for that user (ephemeral+component)
        // We'll allow the user who opened the dashboard to interact for 5 minutes
        const filter = i => i.user.id === interaction.user.id && i.customId.startsWith(`automod:menu:${guildId}`);
        const collector = interaction.channel.createMessageComponentCollector({ filter, time: 5 * 60 * 1000, max: 1 });
        collector.on('collect', async sel => {
          const value = sel.values[0];
          if (value === 'config') {
            const cfg = getCfg(guildId);
            const embed = neoEmbed('Configuration', 'Edit your AutoMod configuration below', [
              { name: 'Log Channel', value: cfg.logChannelId ? `<#${cfg.logChannelId}>` : 'None', inline: true },
              { name: 'NSFW scanning', value: String(!!cfg.nsfwScanEnabled), inline: true },
              { name: 'AutoMod Sync', value: String(!!cfg.automodSync), inline: true }
            ], COLORS.info);
            const row = new ARB().addComponents(
              new ButtonBuilder().setCustomId(`automod:cfg_setlog:${guildId}`).setLabel('Set Log Channel').setStyle(ButtonStyle.Primary),
              new ButtonBuilder().setCustomId(`automod:cfg_toggle_nsfw:${guildId}`).setLabel(cfg.nsfwScanEnabled ? 'Disable NSFW' : 'Enable NSFW').setStyle(ButtonStyle.Secondary),
              new ButtonBuilder().setCustomId(`automod:cfg_toggle_sync:${guildId}`).setLabel(cfg.automodSync ? 'Disable AutoSync' : 'Enable AutoSync').setStyle(ButtonStyle.Secondary)
            );
            await sel.update({ embeds: [embed], components: [row] });
          } else if (value === 'triggers') {
            const cfg = getCfg(guildId);
            const list = (cfg.automodTriggers || []).slice(0, 10).map((t,i)=> `${i+1}. **${t.name||'(no name)'}** • ${t.trigger_type} • \`${t.pattern||''}\` -> ${t.action}`).join('\n') || 'No fallback triggers';
            const embed = neoEmbed('Rules & Triggers', list, [], COLORS.info);
            const row = new ARB().addComponents(
              new ButtonBuilder().setCustomId(`automod:trig_add:${guildId}`).setLabel('Add trigger').setStyle(ButtonStyle.Success),
              new ButtonBuilder().setCustomId(`automod:trig_remove:${guildId}`).setLabel('Remove trigger').setStyle(ButtonStyle.Danger)
            );
            await sel.update({ embeds: [embed], components: [row] });
          } else if (value === 'ai') {
            const cfg = getCfg(guildId);
            const p = cfg.perspectiveThresholds || {};
            const v = cfg.visionThresholds || {};
            const text = Object.entries(p).map(([k,vv]) => `• ${k}: ${vv.threshold} -> ${vv.action}`).join('\n') + '\n\n' + Object.entries(v).map(([k,vv]) => `• ${k}: [${(vv.levels||[]).join(',')}] -> ${vv.action}`).join('\n');
            const embed = neoEmbed('AI Thresholds', text, [], COLORS.accent);
            const row = new ARB().addComponents(
              new ButtonBuilder().setCustomId(`automod:ai_edit:${guildId}`).setLabel('Edit thresholds').setStyle(ButtonStyle.Primary),
              new ButtonBuilder().setCustomId(`automod:ai_test:${guildId}`).setLabel('Run test').setStyle(ButtonStyle.Secondary)
            );
            await sel.update({ embeds: [embed], components: [row] });
          } else if (value === 'logs') {
            const rows = db.prepare('SELECT id,user_id,action,reason,created_at FROM infractions WHERE guild_id = ? ORDER BY id DESC LIMIT 10').all(guildId);
            const lines = rows.map(r => `#${r.id} • <@${r.user_id}> • ${r.action} • ${r.reason} • ${r.created_at}`).join('\n') || 'No infractions yet';
            const embed = neoEmbed('Infractions', lines, [], COLORS.warn);
            await sel.update({ embeds: [embed], components: [] });
          } else if (value === 'sync') {
            const cfg = getCfg(guildId);
            const embed = neoEmbed('AutoMod Sync', `AutoMod sync is ${cfg.automodSync ? 'ENABLED' : 'DISABLED'}. Use the Sync button to (attempt to) mirror fallback rules to Discord native AutoMod.`, [], COLORS.info);
            const row = new ARB().addComponents(
              new ButtonBuilder().setCustomId(`automod:sync_now:${guildId}`).setLabel('Sync now').setStyle(ButtonStyle.Primary)
            );
            await sel.update({ embeds: [embed], components: [row] });
          }
        });
      }
    } catch (e) {
      console.error('interaction error', e);
    }
  });

  c.on('messageCreate', async (msg) => {
    if (!msg.guild || msg.author.bot) return;
    const attachments = Array.from(msg.attachments.values()).map(a => ({ url: a.url, name: a.name }));
    // run scanner and let it take actions
    const res = await scanMessage({ client: c, guildId: msg.guild.id, channelId: msg.channel.id, authorId: msg.author.id, content: msg.content, attachments, messageObj: msg });
    // optionally post a compact log if actioned
    if (res && res.actioned) {
      const embed = neoEmbed('AutoMod actioned', `Actioned: ${res.reason}`, [{ name: 'Category', value: res.category }], COLORS.warn);
      await sendGuildLog(c, msg.guild.id, embed, msg.author.id);
    }
  });

  c.on('interactionCreate', async (i) => {
    if (!i.isButton()) return;
    // moderator buttons handling
    const parts = i.customId.split(':');
    if (parts[0] === 'mod') {
      const action = parts[1];
      const guildId = parts[2];
      const targetUserId = parts[3] === '0' ? null : parts[3];
      // check moderator permission
      const member = await i.guild.members.fetch(i.user.id).catch(()=>null);
      const cfg = getCfg(guildId);
      const isMod = member && (member.permissions.has(PermissionsBitField.Flags.Administrator) || (member.roles.cache && member.roles.cache.some(r=>cfg.modRoleIds.includes(r.id))));
      if (!isMod) { await i.reply({ content: 'Permission denied', ephemeral: true }); return; }
      if (action === 'warn') {
        if (!targetUserId) { await i.reply({ content: 'No target', ephemeral: true }); return; }
        try {
          const g = await c.guilds.fetch(guildId);
          const m = await g.members.fetch(targetUserId);
          await m.send({ embeds: [neoEmbed('Moderation: Warn', `You were warned in ${g.name}`)] }).catch(()=>{});
          addInfraction(guildId, targetUserId, i.user.id, 'warn', 'Moderator manual warn');
          await i.reply({ content: `Warned <@${targetUserId}>`, ephemeral: true });
        } catch (e) { await i.reply({ content: 'Failed to warn', ephemeral: true }); }
      } else if (action === 'delete') {
        addInfraction(guildId, targetUserId||'unknown', i.user.id, 'delete', 'Moderator requested delete (manual)');
        await i.reply({ content: 'Recorded delete (manual).', ephemeral: true });
      } else if (action === 'mute') {
        // temp mute 60s
        try {
          const g = await c.guilds.fetch(guildId);
          const m = await g.members.fetch(targetUserId);
          await m.timeout(60*1000, `Moderator manual mute`);
          addInfraction(guildId, targetUserId, i.user.id, 'temp_mute', 'Moderator manual mute 60s');
          await i.reply({ content: `Muted <@${targetUserId}> for 60s.`, ephemeral: true });
        } catch (e) { await i.reply({ content: 'Failed to mute', ephemeral: true }); }
      } else if (action === 'kick') {
        try { const g = await c.guilds.fetch(guildId); await g.members.kick(targetUserId, 'Moderator manual kick'); addInfraction(guildId, targetUserId, i.user.id, 'kick', 'Moderator manual kick'); await i.reply({ content: `Kicked <@${targetUserId}>`, ephemeral: true }); } catch (e) { await i.reply({ content: 'Failed to kick', ephemeral: true }); }
      } else if (action === 'ban') {
        try { const g = await c.guilds.fetch(guildId); await g.bans.create(targetUserId, { reason: 'Moderator manual ban' }); addInfraction(guildId, targetUserId, i.user.id, 'ban', 'Moderator manual ban'); await i.reply({ content: `Banned <@${targetUserId}>`, ephemeral: true }); } catch (e) { await i.reply({ content: 'Failed to ban', ephemeral: true }); }
      }
    }

    // dashboard config buttons
    if (i.customId.startsWith('automod:')) {
      const parts = i.customId.split(':');
      const action = parts[1];
      const guildId = parts[2];
      if (action === 'cfg_toggle_nsfw') {
        const cfg = getCfg(guildId); cfg.nsfwScanEnabled = !cfg.nsfwScanEnabled; setCfg(guildId, cfg);
        await i.update({ embeds: [neoEmbed('Config updated', `NSFW scanning is now ${cfg.nsfwScanEnabled}`)], components: [] });
      } else if (action === 'cfg_toggle_sync') {
        const cfg = getCfg(guildId); cfg.automodSync = !cfg.automodSync; setCfg(guildId, cfg);
        await i.update({ embeds: [neoEmbed('Config updated', `AutoMod sync is now ${cfg.automodSync}`)], components: [] });
      } else if (action === 'sync_now') {
        await i.update({ embeds: [neoEmbed('Sync', 'Attempting to sync fallback rules to Discord native AutoMod (best-effort)...')], components: [] });
        // sync logic placeholder: requires REST calls to guild API (advanced) — we will attempt a read-only listing for now
        try {
          // Note: full create/edit requires additional scopes and per-guild endpoints; left as "opt-in" later
          await i.followUp({ content: 'Sync attempted (read only). Implement full sync via automodSync flag and ensure bot has proper permissions.', ephemeral: true });
        } catch (e) { await i.followUp({ content: 'Sync failed: ' + e.message, ephemeral: true }); }
      } else if (action === 'trig_add') {
        // open modal to add trigger
        const modal = new ModalBuilder().setCustomId(`automod:modal_addtrigger:${guildId}`).setTitle('Add fallback trigger');
        const nameInput = new TextInputBuilder().setCustomId('name').setLabel('Rule name').setStyle(TextInputStyle.Short).setPlaceholder('e.g. block-invites').setRequired(true);
        const typeInput = new TextInputBuilder().setCustomId('type').setLabel('Trigger type').setStyle(TextInputStyle.Short).setPlaceholder('keyword|regex|invite').setRequired(true);
        const patternInput = new TextInputBuilder().setCustomId('pattern').setLabel('Pattern / keywords').setStyle(TextInputStyle.Paragraph).setPlaceholder('pattern or comma-separated keywords').setRequired(false);
        const actionInput = new TextInputBuilder().setCustomId('action').setLabel('Action').setStyle(TextInputStyle.Short).setPlaceholder('delete+warn or temp_mute:300').setRequired(true);
        modal.addComponents(new ActionRowBuilder().addComponents(nameInput), new ActionRowBuilder().addComponents(typeInput), new ActionRowBuilder().addComponents(patternInput), new ActionRowBuilder().addComponents(actionInput));
        await i.showModal(modal);
        // modal submit handling is automatic under client.on('interactionCreate'), which we didn't add for modals due to brevity.
      }
    }
  });

  await c.login(BOT_TOKEN).catch(e => { console.error('discord login failed', e); process.exit(1); });
  client = c;
  return c;
}

// ----------------- Microservice: stdin/stdout JSON RPC -----------------
const pendingResponses = new Map();
function sendJson(obj) {
  process.stdout.write(JSON.stringify(obj) + '\n');
}

async function handleRpcLine(line) {
  if (!line) return;
  let msg;
  try { msg = JSON.parse(line); } catch (e) { sendJson({ id: null, ok: false, error: 'invalid json' }); return; }
  const id = msg.id || null;
  try {
    if (msg.cmd === 'health') {
      sendJson({ id, ok: true, result: { status: 'ok', pid: process.pid } });
      return;
    } else if (msg.cmd === 'scan_message') {
      const data = msg.data || {};
      const res = await scanMessage({ client, guildId: data.guild_id, channelId: data.channel_id, authorId: data.author_id, content: data.content, attachments: data.attachments || [], messageObj: null });
      sendJson({ id, ok: true, result: res });
      return;
    } else if (msg.cmd === 'get_config') {
      const gid = msg.data && msg.data.guild_id;
      if (!gid) { sendJson({ id, ok: false, error: 'guild_id required' }); return; }
      const cfg = getCfg(gid);
      sendJson({ id, ok: true, result: cfg });
      return;
    } else if (msg.cmd === 'reload') {
      // placeholder
      sendJson({ id, ok: true, result: 'reloaded' });
      return;
    } else {
      sendJson({ id, ok: false, error: 'unknown_cmd' });
      return;
    }
  } catch (e) {
    sendJson({ id, ok: false, error: e && e.message });
  }
}

if (require.main === module) {
  // start client if token present
  (async () => {
    if (BOT_TOKEN) {
      await startDiscordClient().catch(e => console.error('client start fail', e));
    } else {
      console.log('BOT_TOKEN not provided; running in microservice mode (no Discord client).');
    }

    // stdin line reader. Accept newline-delimited JSON
    let buffer = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', chunk => {
      buffer += chunk;
      let idx;
      while ((idx = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, idx).trim();
        buffer = buffer.slice(idx + 1);
        if (line) handleRpcLine(line);
      }
    });
    process.stdin.on('end', () => { process.exit(0); });
  })();
}

// Export for programmatic usage (e.g., require)
module.exports = { scanMessage, getCfg, setCfg, startDiscordClient };
