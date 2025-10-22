/**
 * cogs/automod.js (initial)
 *
 * Discord AutoMod module (converted from Python cog to JavaScript Because AI integration with Python is not very Compatable+doesnt work well)
 *
 * Features:
 *  - Guild-specific storage of automod config and infractions (SQLite)
 *  - Banned words, spam detection, link whitelist/blacklist, language enforcement
 *  - Perspective API (text) moderation integration with per-category thresholds
 *  - Google Vision SafeSearch (image) moderation integration
 *  - Per-category thresholds and per-category automatic actions (configurable)
 *  - Message pipeline integrates image scanning and text scanning
 *  - Moderator log embeds with interactive moderator buttons
 *  - Slash command group: /automod add_trigger, remove_trigger, list_triggers, config, test
 *
 * Environment variables:
 *  - SQLITE_DB_PATH: (optional) SQLite DB path; default: automod_bot.db
 *  - GOOGLE_VISION_KEY: API key for Google Cloud Vision (images)
 *  - PERSPECTIVE_KEY: API key for Google Perspective API (text)
 * Call `await setup(client)` from your loader to register commands and listeners.
 */

const { Client, GatewayIntentBits, Partials, EmbedBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle, PermissionsBitField, ChannelType } = require('discord.js');
const { REST } = require('@discordjs/rest');
const { Routes } = require('discord-api-types/v10');
const { SlashCommandBuilder } = require('@discordjs/builders');
const sqlite = require('sqlite');
const sqlite3 = require('sqlite3');
const fetch = require('node-fetch');
const path = require('path');
const fs = require('fs');

const SQLITE_DB_PATH = process.env.SQLITE_DB_PATH || path.join(process.cwd(), 'automod_bot.db');
const GOOGLE_VISION_KEY = process.env.GOOGLE_VISION_KEY || null;
const PERSPECTIVE_KEY = process.env.PERSPECTIVE_KEY || null;

const EMOJI_SUCCESS = '✅';
const EMOJI_WARNING = '⚠️';
const EMOJI_ERROR = '❌';

const COLORS = {
  success: 0x2ecc71,
  warning: 0xf39c12,
  error: 0xe74c3c,
  info: 0x3498db,
};

// Default per-guild config
const DEFAULT_AUTOMOD_CFG = {
  logChannelId: null,
  modRoleIds: [],         // role IDs that can manage automod
  trustedRoleIds: [],     // exempt roles
  bannedWords: [],        // substring matches (case-insensitive)
  automodTriggers: [],    // fallback triggers when native automod unsupported
  spamThreshold: { messages: 5, seconds: 8 },
  linksWhitelist: [],
  linksBlacklist: [],
  nsfwScanEnabled: false,
  languageEnforcedChannels: {}, // { channelId: languageCode }
  muteRoleId: null,
  tempMutes: [],          // [{userId, unmuteAtIso, reason, moderatorId}]
  customRules: [],
  // Perspective thresholds (default): map category -> { threshold: float, action: "delete+warn" }
  perspectiveThresholds: {
    TOXICITY: { threshold: 0.85, action: 'delete+warn' },
    SEVERE_TOXICITY: { threshold: 0.85, action: 'delete+warn' },
    INSULT: { threshold: 0.85, action: 'delete+warn' },
    IDENTITY_ATTACK: { threshold: 0.85, action: 'delete+warn' },
    THREAT: { threshold: 0.80, action: 'delete+warn' },
    SEXUALLY_EXPLICIT: { threshold: 0.80, action: 'delete+warn' },
  },
  // Vision SafeSearch thresholds: map category -> action if flagged
  visionThresholds: {
    adult: { likelihoods: ['LIKELY', 'VERY_LIKELY'], action: 'delete+warn' },
    violence: { likelihoods: ['LIKELY', 'VERY_LIKELY'], action: 'delete+warn' },
    racy: { likelihoods: ['LIKELY', 'VERY_LIKELY'], action: 'delete+warn' },
  },
};

let db = null; // sqlite database instance

// ------------ Helpers: DB Layer ------------
async function initDb() {
  if (db) return;
  // Ensure folder exists
  const dir = path.dirname(SQLITE_DB_PATH);
  if (!fs.existsSync(dir) && dir !== '.') {
    fs.mkdirSync(dir, { recursive: true });
  }
  db = await sqlite.open({ filename: SQLITE_DB_PATH, driver: sqlite3.Database });
  await db.exec(`
    CREATE TABLE IF NOT EXISTS guilds (
      guild_id INTEGER PRIMARY KEY,
      config TEXT NOT NULL
    );
  `);
  await db.exec(`
    CREATE TABLE IF NOT EXISTS infractions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      guild_id INTEGER NOT NULL,
      user_id INTEGER NOT NULL,
      moderator_id INTEGER,
      action TEXT NOT NULL,
      reason TEXT,
      created_at TEXT NOT NULL
    );
  `);
}

async function ensureGuildCfg(guildId) {
  await initDb();
  const row = await db.get('SELECT config FROM guilds WHERE guild_id = ?', guildId);
  if (!row) {
    await setGuildConfig(guildId, DEFAULT_AUTOMOD_CFG);
  }
}

async function getGuildConfig(guildId) {
  await initDb();
  const row = await db.get('SELECT config FROM guilds WHERE guild_id = ?', guildId);
  if (row) {
    try {
      return JSON.parse(row.config);
    } catch (e) {
      return JSON.parse(JSON.stringify(DEFAULT_AUTOMOD_CFG));
    }
  } else {
    await setGuildConfig(guildId, DEFAULT_AUTOMOD_CFG);
    return JSON.parse(JSON.stringify(DEFAULT_AUTOMOD_CFG));
  }
}

async function setGuildConfig(guildId, config) {
  await initDb();
  const cfgText = JSON.stringify(config);
  await db.run(`INSERT INTO guilds (guild_id, config) VALUES (?, ?)
    ON CONFLICT(guild_id) DO UPDATE SET config = excluded.config`, [guildId, cfgText]);
}

async function addInfraction(guildId, userId, moderatorId, action, reason) {
  await initDb();
  const now = new Date().toISOString();
  await db.run(`INSERT INTO infractions (guild_id, user_id, moderator_id, action, reason, created_at)
     VALUES (?, ?, ?, ?, ?, ?)`, [guildId, userId, moderatorId || null, action, reason || null, now]);
}

async function getRecentInfractions(guildId, limit = 200) {
  await initDb();
  return await db.all('SELECT id, user_id, moderator_id, action, reason, created_at FROM infractions WHERE guild_id = ? ORDER BY id DESC LIMIT ?', [guildId, limit]);
}

// ------------ Helpers: Aesthetic embed maker ------------
function makeEmbed(type, title, description, fields = []) {
  const color = COLORS[type] || COLORS.info;
  const em = new EmbedBuilder()
    .setTitle(title)
    .setDescription(description)
    .setColor(color)
    .setTimestamp(new Date());
  for (const f of fields) {
    // f = {name, value, inline}
    em.addFields([{ name: f.name, value: f.value, inline: !!f.inline }]);
  }
  return em;
}

// ------------ Helpers: utilities ------------
function extractDomainsFromText(content = '') {
  const regex = /https?:\/\/[^\s/$.?#].[^\s]*/gi;
  const found = content.match(regex) || [];
  const domains = found.map(u => {
    const m = u.match(/^https?:\/\/([^/]+)/i);
    return m ? m[1].toLowerCase() : null;
  }).filter(Boolean);
  return domains;
}

function domainInPatterns(domain, patterns = []) {
  if (!domain) return false;
  domain = domain.toLowerCase();
  for (const p of patterns) {
    if (!p) continue;
    if (domain.includes(p.trim().toLowerCase())) return true;
  }
  return false;
}

function detectLanguageStub(text = '') {
  // Naive detection to match Python stub
  const t = text.toLowerCase();
  if (t.includes(' the ') || t.includes(' and ') || t.includes(' is ') || t.includes(' you ')) return 'en';
  if (t.includes(' el ') || t.includes(' la ') || t.includes(' y ') || t.includes(' que ')) return 'es';
  if (t.includes(' le ') || t.includes(' la ') || t.includes(' est ') || t.includes(' et ')) return 'fr';
  return 'unknown';
}

// map Vision likelihood strings to index severity for simple comparison
const VISION_LIKELIKHOODS = ['UNKNOWN', 'VERY_UNLIKELY', 'UNLIKELY', 'POSSIBLE', 'LIKELY', 'VERY_LIKELY'];
function visionLikelihoodIndex(l) {
  return VISION_LIKELIKHOODS.indexOf(l || 'UNKNOWN');
}

// ------------ Perspective API integration ------------
async function analyzeTextPerspective(text) {
  if (!PERSPECTIVE_KEY) return null;
  try {
    const url = `https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze?key=${PERSPECTIVE_KEY}`;
    const body = {
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
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const textErr = await res.text();
      console.warn('Perspective API returned non-ok:', res.status, textErr);
      return null;
    }
    const json = await res.json();
    // Parse attribute scores into a simpler map
    const out = {};
    const attrs = json.attributeScores || {};
    for (const [k, v] of Object.entries(attrs)) {
      const summaryScore = (v && v.summaryScore && typeof v.summaryScore.value === 'number') ? v.summaryScore.value : null;
      out[k] = summaryScore;
    }
    return out;
  } catch (err) {
    console.error('Perspective error', err);
    return null;
  }
}

// ------------ Google Vision SafeSearch integration ------------
async function analyzeImageSafeSearchBase64(base64Image) {
  if (!GOOGLE_VISION_KEY) return null;
  try {
    const url = `https://vision.googleapis.com/v1/images:annotate?key=${GOOGLE_VISION_KEY}`;
    const payload = {
      requests: [
        {
          image: { content: base64Image },
          features: [{ type: 'SAFE_SEARCH_DETECTION' }],
        }
      ]
    };
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      console.warn('Vision API non-ok', await res.text());
      return null;
    }
    const json = await res.json();
    const resp = json.responses && json.responses[0];
    if (!resp) return null;
    const safe = resp.safeSearchAnnotation || {};
    // safe has adult, violence, racy, medical, spoof values as strings like VERY_LIKELY
    return safe;
  } catch (err) {
    console.error('Vision API error', err);
    return null;
  }
}

// Helper: fetch attachment as base64 (small images only)
async function fetchAttachmentAsBase64(url) {
  try {
    const r = await fetch(url);
    if (!r.ok) return null;
    const buffer = await r.arrayBuffer();
    return Buffer.from(buffer).toString('base64');
  } catch (e) {
    return null;
  }
}

// ------------ Moderation actions ------------
async function warnUserSendDM(targetMember, guild, reason) {
  const embed = makeEmbed('warning', 'You received a warning', `You were warned in **${guild.name}**.\n\n**Reason:** ${reason}`);
  try {
    await targetMember.send({ embeds: [embed] });
  } catch (e) {
    // ignore DM errors
  }
}

async function deleteAndLog(client, message, reason, moderator = null) {
  try { await message.delete(); } catch (e) {}
  await addInfraction(message.guild.id, message.author.id, moderator ? moderator.id : null, 'delete', reason);
  const moderatorMention = moderator ? `<@${moderator.id}>` : 'AutoMod';
  const fields = [
    { name: 'Moderator', value: moderatorMention, inline: true },
    { name: 'Channel', value: `<#${message.channel.id}>`, inline: true },
    { name: 'Reason', value: reason, inline: false },
    { name: 'Content', value: message.content ? message.content.slice(0, 1000) : '[no content]', inline: false },
  ];
  const em = makeEmbed('warning', 'Message Deleted', `Message by <@${message.author.id}> deleted.`, fields);
  await sendLogToGuild(message.guild, client, em, message.author.id);
}

async function applyTempMute(client, guild, member, seconds, reason, moderator = null) {
  // Ensure mute role exists in config
  const cfg = await getGuildConfig(guild.id);
  let muteRole = guild.roles.cache.get(cfg.muteRoleId);
  if (!muteRole) {
    try {
      muteRole = await guild.roles.create({ name: 'Muted', reason: 'AutoMod - create Muted role' });
    } catch (e) {
      muteRole = null;
    }
    if (muteRole) {
      // set channel overwrites best-effort
      for (const ch of guild.channels.cache.values()) {
        if (ch.type === ChannelType.GuildText) {
          try {
            await ch.permissionOverwrites.create(muteRole, { SendMessages: false, AddReactions: false });
          } catch (e) {}
        }
      }
      cfg.muteRoleId = muteRole.id;
      await setGuildConfig(guild.id, cfg);
    }
  }
  try {
    if (muteRole) {
      await member.roles.add(muteRole, `Temp mute: ${reason}`);
    } else {
      // try server-wide timeout if supported
      if (typeof member.timeout === 'function' || typeof member.timeoutUntil === 'function') {
        try {
          const until = new Date(Date.now() + seconds * 1000);
          if (member.timeout) await member.timeout(seconds * 1000, reason); // discord.js v14 maybe
        } catch (e) {}
      }
    }
  } catch (e) {}
  // Persist in config
  const unmuteAtIso = new Date(Date.now() + seconds * 1000).toISOString();
  const tms = cfg.tempMutes || [];
  tms.push({ userId: member.id, unmuteAtIso, reason, moderatorId: moderator ? moderator.id : null });
  cfg.tempMutes = tms;
  await setGuildConfig(guild.id, cfg);
  await addInfraction(guild.id, member.id, moderator ? moderator.id : null, 'temp_mute', reason);
  const em = makeEmbed('warning', 'Temp mute applied', `<@${member.id}> was muted for ${seconds} seconds.`, [{ name: 'Reason', value: reason, inline: false }]);
  await sendLogToGuild(guild, client, em, member.id);
  try {
    await member.send({ embeds: [makeEmbed('warning', 'You were muted', `You were muted for ${seconds} seconds in **${guild.name}**.\n\nReason: ${reason}`)] });
  } catch (e) {}
}

async function unmuteMember(client, guild, userId) {
  const cfg = await getGuildConfig(guild.id);
  const muteRoleId = cfg.muteRoleId;
  const member = await guild.members.fetch(userId).catch(() => null);
  if (member && muteRoleId) {
    const role = guild.roles.cache.get(muteRoleId);
    if (role) {
      try { await member.roles.remove(role, 'Auto unmute (temp mute expired)'); } catch (e) {}
    }
  }
  // remove from config tempMutes
  const tms = (cfg.tempMutes || []).filter(t => t.userId !== userId);
  cfg.tempMutes = tms;
  await setGuildConfig(guild.id, cfg);
  await sendLogToGuild(guild, client, makeEmbed('success', 'User unmuted', `<@${userId}> unmuted (auto).`), userId);
}

async function maybeEscalate(client, guild, member) {
  const rows = await getRecentInfractions(guild.id, 200);
  const count = rows.filter(r => r.user_id === member.id).length;
  if (count >= 6) {
    await applyTempMute(client, guild, member, 86400, 'Escalation: repeated infractions');
  } else if (count >= 3) {
    await applyTempMute(client, guild, member, 600, 'Escalation: repeated infractions');
  }
}

// ------------ Logging channel + interactive moderator buttons ------------
/**
 * Send a moderator log embed to configured guild log channel.
 * Adds interactive buttons that moderators can press to apply actions on the user:
 *  - Warn (sends DM & records)
 *  - Temp Mute (60s default)
 *  - Delete Message
 *  - Kick
 *  - Ban
 *
 * For any button interactions, only users that pass _isModerator check in the guild are permitted to use them.
 */
async function sendLogToGuild(guild, client, embed, targetUserId = null, extra = {}) {
  try {
    const cfg = await getGuildConfig(guild.id);
    const logId = cfg.logChannelId;
    if (!logId) return;
    const ch = await guild.channels.fetch(logId).catch(() => null);
    if (!ch || !(ch.isTextBased && ch.viewable)) return;
    const buttons = new ActionRowBuilder().addComponents(
      new ButtonBuilder().setCustomId(`mod_warn:${guild.id}:${targetUserId || '0'}`).setLabel('Warn').setStyle(ButtonStyle.Primary),
      new ButtonBuilder().setCustomId(`mod_temp_mute:${guild.id}:${targetUserId || '0'}`).setLabel('Temp Mute').setStyle(ButtonStyle.Secondary),
      new ButtonBuilder().setCustomId(`mod_delete:${guild.id}:${targetUserId || '0'}`).setLabel('Delete Msg').setStyle(ButtonStyle.Danger),
      new ButtonBuilder().setCustomId(`mod_kick:${guild.id}:${targetUserId || '0'}`).setLabel('Kick').setStyle(ButtonStyle.Danger),
      new ButtonBuilder().setCustomId(`mod_ban:${guild.id}:${targetUserId || '0'}`).setLabel('Ban').setStyle(ButtonStyle.Danger),
    );
    await ch.send({ embeds: [embed], components: [buttons] });
  } catch (e) {
    // ignore log errors
    console.error('Failed sendLogToGuild', e);
  }
}

// Interaction handler for moderator buttons; only allow configured moderators or guild admins.
async function handleModeratorButton(interaction) {
  try {
    if (!interaction.isButton()) return;
    const [action, guildIdStr, targetUserIdStr] = interaction.customId.split(':');
    const guild = interaction.guild;
    if (!guild || guild.id !== guildIdStr) {
      await interaction.reply({ content: 'This button does not belong to this guild.', ephemeral: true });
      return;
    }
    const cfg = await getGuildConfig(guild.id);
    // is moderator?
    const member = interaction.member;
    const modRoles = cfg.modRoleIds || [];
    let isMod = false;
    if (guild.ownerId === member.user.id) isMod = true;
    if (member.permissions.has(PermissionsBitField.Flags.Administrator)) isMod = true;
    for (const r of member.roles.cache.values()) {
      if (modRoles.includes(r.id)) { isMod = true; break; }
    }
    if (!isMod) {
      await interaction.reply({ content: 'You are not a configured moderator for this server.', ephemeral: true });
      return;
    }

    const targetUserId = targetUserIdStr && targetUserIdStr !== '0' ? targetUserIdStr : null;
    const targetMember = targetUserId ? await guild.members.fetch(targetUserId).catch(() => null) : null;

    // Run action
    if (action === 'mod_warn') {
      if (targetMember) {
        await warnUserSendDM(targetMember, guild, 'Actioned by moderator via log button');
        await addInfraction(guild.id, targetMember.id, interaction.user.id, 'warn', 'Moderator-button warn');
        await interaction.reply({ content: `Warned <@${targetMember.id}>.`, ephemeral: true });
      } else {
        await interaction.reply({ content: 'Target user not found', ephemeral: true });
      }
      return;
    }
    if (action === 'mod_temp_mute') {
      if (targetMember) {
        await applyTempMute(interaction.client, guild, targetMember, 60, 'Moderator-button temp mute', interaction.member);
        await interaction.reply({ content: `Temporarily muted <@${targetMember.id}> for 60s.`, ephemeral: true });
      } else {
        await interaction.reply({ content: 'Target user not found', ephemeral: true });
      }
      return;
    }
    if (action === 'mod_delete') {
      // The log doesn't have the message reference sent to it, so we can only record an infraction & mention the moderator did a delete.
      await addInfraction(guild.id, targetUserId || 0, interaction.user.id, 'delete', 'Moderator-button delete (manual)');
      await interaction.reply({ content: `Recorded delete action for user ${targetUserId ? `<@${targetUserId}>` : 'unknown'}.`, ephemeral: true });
      return;
    }
    if (action === 'mod_kick') {
      if (targetMember) {
        try {
          await targetMember.kick('Moderator-button kick');
          await addInfraction(guild.id, targetMember.id, interaction.user.id, 'kick', 'Moderator-button kick');
          await interaction.reply({ content: `Kicked <@${targetMember.id}>.`, ephemeral: true });
        } catch (e) {
          await interaction.reply({ content: `Failed to kick: ${e.message}`, ephemeral: true });
        }
      } else {
        await interaction.reply({ content: 'Target user not found', ephemeral: true });
      }
      return;
    }
    if (action === 'mod_ban') {
      if (targetMember) {
        try {
          await targetMember.ban({ reason: 'Moderator-button ban' });
          await addInfraction(guild.id, targetMember.id, interaction.user.id, 'ban', 'Moderator-button ban');
          await interaction.reply({ content: `Banned <@${targetMember.id}>.`, ephemeral: true });
        } catch (e) {
          await interaction.reply({ content: `Failed to ban: ${e.message}`, ephemeral: true });
        }
      } else {
        await interaction.reply({ content: 'Target user not found', ephemeral: true });
      }
      return;
    }
  } catch (err) {
    console.error('handleModeratorButton error', err);
    try { if (!interaction.replied) await interaction.reply({ content: 'Error handling button', ephemeral: true }); } catch (e) {}
  }
}

// ------------ Spam cache & unmute watcher ------------
const spamCache = new Map(); // guildId -> Map userId -> timestamps[]
let unmuteWatcherInterval = null;
async function startUnmuteWatcher(client) {
  if (unmuteWatcherInterval) return;
  await initDb();
  unmuteWatcherInterval = setInterval(async () => {
    try {
      const rows = await db.all('SELECT guild_id, config FROM guilds');
      const now = new Date();
      for (const row of rows) {
        let cfg;
        try { cfg = JSON.parse(row.config); } catch (e) { continue; }
        const tms = cfg.tempMutes || [];
        let changed = false;
        for (const tm of [...tms]) {
          if (!tm.unmuteAtIso) continue;
          const unmuteAt = new Date(tm.unmuteAtIso);
          if (unmuteAt <= now) {
            const guild = client.guilds.cache.get(row.guild_id);
            if (guild) {
              await unmuteMember(client, guild, tm.userId).catch(() => {});
            }
            // remove entry
            const idx = tms.indexOf(tm);
            if (idx >= 0) {
              tms.splice(idx, 1);
              changed = true;
            }
          }
        }
        if (changed) {
          cfg.tempMutes = tms;
          await db.run('INSERT INTO guilds (guild_id, config) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET config = excluded.config', [row.guild_id, JSON.stringify(cfg)]);
        }
      }
    } catch (e) {
      console.error('unmute watcher error', e);
    }
  }, 15 * 1000);
}

// ------------ Main message pipeline ------------
/**
 * Pipeline steps:
 *  1) ignore bots & DMs
 *  2) ensure guild config
 *  3) banned words -> delete + warn + escalate
 *  4) custom DB rules
 *  5) spam detection -> delete/warn/temp-mute
 *  6) link protection
 *  7) image scanning via Vision SafeSearch -> take action using visionThresholds
 *  8) Perspective text moderation -> per-category action if threshold crossed
 *  9) language enforcement
 *  10) DB fallback triggers
 */
async function onMessageCreate(client, message) {
  if (!message.guild || message.author.bot) return;
  await ensureGuildCfg(message.guild.id);
  const cfg = await getGuildConfig(message.guild.id);
  const content = message.content || '';

  // TRUSTED? skip if user is in trusted roles
  const member = message.member;
  let isTrusted = false;
  if (member) {
    if (message.guild.ownerId === member.id) isTrusted = true;
    if (member.permissions.has(PermissionsBitField.Flags.Administrator)) isTrusted = true;
    (member.roles.cache || []).forEach(r => { if (cfg.trustedRoleIds && cfg.trustedRoleIds.includes(r.id)) isTrusted = true; });
  }
  if (isTrusted) return;

  // 1) Banned words
  for (const bad of (cfg.bannedWords || [])) {
    if (!bad) continue;
    if (content.toLowerCase().includes(bad.toLowerCase())) {
      const reason = `banned_word:${bad}`;
      await deleteAndLog(client, message, reason, null);
      if (member) await warnUserSendDM(member, message.guild, `Use of banned word: ${bad}`);
      await maybeEscalate(client, message.guild, member);
      return;
    }
  }

  // 2) Custom DB rules
  for (const rule of (cfg.customRules || [])) {
    const ttype = rule.trigger_type;
    const pattern = rule.pattern || '';
    const action = rule.action || 'warn';
    let matched = false;
    try {
      if (ttype === 'contains' && content.toLowerCase().includes(pattern.toLowerCase())) matched = true;
      else if (ttype === 'regex' && new RegExp(pattern, 'i').test(content)) matched = true;
      else if (ttype === 'invite' && (content.toLowerCase().includes('discord.gg/') || content.toLowerCase().includes('discord.com/invite/'))) matched = true;
    } catch (e) {
      matched = false;
    }
    if (matched) {
      const reason = `custom_rule:${ttype}:${pattern}`;
      await executeRuleAction(client, message, action, reason);
      return;
    }
  }

  // 3) Spam detection
  const spamCfg = cfg.spamThreshold || { messages: 5, seconds: 8 };
  const thrMsgs = Number(spamCfg.messages || 5);
  const thrSecs = Number(spamCfg.seconds || 8);
  const nowTs = Date.now() / 1000;
  if (!spamCache.has(message.guild.id)) spamCache.set(message.guild.id, new Map());
  const guildCache = spamCache.get(message.guild.id);
  if (!guildCache.has(message.author.id)) guildCache.set(message.author.id, []);
  const userTimes = guildCache.get(message.author.id);
  userTimes.push(nowTs);
  const windowStart = nowTs - thrSecs;
  const kept = userTimes.filter(t => t >= windowStart);
  guildCache.set(message.author.id, kept);
  if (kept.length >= thrMsgs) {
    const reason = `spam:${kept.length} in ${thrSecs}s`;
    await deleteAndLog(client, message, reason, null);
    if (member) await warnUserSendDM(member, message.guild, 'Spam detected: too many messages in a short timeframe.');
    if (member) await applyTempMute(client, message.guild, member, 60, 'Spam auto-mute', null);
    guildCache.set(message.author.id, []);
    return;
  }

  // 4) Link protection
  if (content.toLowerCase().includes('http://') || content.toLowerCase().includes('https://')) {
    const domains = extractDomainsFromText(content);
    for (const d of domains) {
      if (domainInPatterns(d, cfg.linksBlacklist || [])) {
        const reason = 'link_blacklisted';
        await deleteAndLog(client, message, reason, null);
        if (member) await warnUserSendDM(member, message.guild, 'Posting blacklisted links is prohibited.');
        await maybeEscalate(client, message.guild, member);
        return;
      }
    }
    if ((cfg.linksWhitelist || []).length > 0) {
      const allowed = domains.some(d => domainInPatterns(d, cfg.linksWhitelist || []));
      if (!allowed && domains.length) {
        const reason = 'link_not_whitelisted';
        await deleteAndLog(client, message, reason, null);
        if (member) await warnUserSendDM(member, message.guild, 'Posting links outside the whitelist is not allowed.');
        return;
      }
    }
  }

  // 5) Image scanning (Vision SafeSearch) integrated into pipeline
  if ((cfg.nsfwScanEnabled || false) && (message.attachments && message.attachments.size > 0)) {
    for (const att of message.attachments.values()) {
      // fetch small images as base64
      const base64 = await fetchAttachmentAsBase64(att.url);
      const safe = base64 ? await analyzeImageSafeSearchBase64(base64) : nsfwStubAnalysis(att.url);
      if (!safe) continue;
      // Check categories against thresholds configured
      const vthresholds = cfg.visionThresholds || DEFAULT_AUTOMOD_CFG.visionThresholds;
      let flagged = false;
      for (const cat of ['adult', 'violence', 'racy']) {
        const val = safe[cat];
        if (!val) continue;
        // if val is in configured likelihoods, flag
        const cfgEntry = vthresholds[cat];
        if (cfgEntry && cfgEntry.likelihoods && cfgEntry.likelihoods.includes(val)) {
          flagged = true;
          const reason = `vision_${cat}:${val}`;
          await executeRuleAction(client, message, cfgEntry.action || 'delete+warn', reason);
          break;
        }
      }
      if (flagged) return;
    }
  }

  // 6) Perspective API text moderation
  if (content && content.length > 3 && PERSPECTIVE_KEY) {
    const scores = await analyzeTextPerspective(content);
    if (scores) {
      // iterate configured thresholds
      const pThresholds = cfg.perspectiveThresholds || DEFAULT_AUTOMOD_CFG.perspectiveThresholds;
      for (const [cat, entry] of Object.entries(pThresholds)) {
        const score = scores[cat];
        if (score != null && score >= (entry.threshold || 0.85)) {
          const reason = `perspective_${cat}:${score}`;
          await executeRuleAction(client, message, entry.action || 'delete+warn', reason);
          return;
        }
      }
    }
  }

  // 7) Language enforcement
  const lec = cfg.languageEnforcedChannels || {};
  const chLang = lec[message.channel.id];
  if (chLang) {
    const detected = detectLanguageStub(content);
    if (detected !== chLang && detected !== 'unknown') {
      const reason = `language_violation expected:${chLang} detected:${detected}`;
      await deleteAndLog(client, message, reason, null);
      if (member) await warnUserSendDM(member, message.guild, `Please use the configured language (${chLang}) in this channel.`);
      return;
    }
  }

  // 8) DB fallback triggers
  for (const trig of (cfg.automodTriggers || [])) {
    const ttype = trig.trigger_type || trig.ttype;
    const pattern = trig.pattern || '';
    const action = trig.action || 'warn';
    let matched = false;
    try {
      if (ttype === 'keyword' || ttype === 'contains') {
        if (pattern && content.toLowerCase().includes(pattern.toLowerCase())) matched = true;
      } else if (ttype === 'regex') {
        if (new RegExp(pattern, 'i').test(content)) matched = true;
      } else if (ttype === 'invite') {
        if (content.toLowerCase().includes('discord.gg/') || content.toLowerCase().includes('discord.com/invite/')) matched = true;
      }
    } catch (e) { matched = false; }
    if (matched) {
      const reason = `db_trigger:${ttype}:${pattern}`;
      await executeRuleAction(client, message, action, reason);
      return;
    }
  }

  // End pipeline
}

// Helper: execute an action string like "delete+warn+temp_mute:300"
async function executeRuleAction(client, message, actionStr, reason) {
  const parts = actionStr.split('+').map(x => x.trim());
  const guild = message.guild;
  const author = message.member;
  const moderator = null;
  for (const actRaw of parts) {
    if (actRaw.startsWith('temp_mute')) {
      let sec = 300;
      if (actRaw.includes(':')) {
        const p = actRaw.split(':', 2)[1];
        sec = parseInt(p) || 300;
      }
      await deleteAndLog(client, message, reason, moderator);
      if (author) await applyTempMute(client, guild, author, sec, reason, moderator);
    } else if (actRaw === 'delete') {
      await deleteAndLog(client, message, reason, moderator);
    } else if (actRaw === 'warn') {
      if (author) {
        await warnUserSendDM(author, guild, reason);
        await addInfraction(guild.id, author.id, moderator ? moderator.id : null, 'warn', reason);
        await sendLogToGuild(guild, client, makeEmbed('warning', 'User warned', `<@${author.id}> warned.`, [{ name: 'Reason', value: reason, inline: false }]), author.id);
      }
    } else if (actRaw === 'kick') {
      try {
        if (author) await author.kick(reason);
        await addInfraction(guild.id, author.id, null, 'kick', reason);
        await sendLogToGuild(guild, client, makeEmbed('warning', 'User kicked', `<@${author.id}> kicked by AutoMod`, [{ name: 'Reason', value: reason, inline: false }]), author.id);
      } catch (e) {}
    } else if (actRaw === 'ban') {
      try {
        if (author) await guild.bans.create(author.id, { reason });
        await addInfraction(guild.id, author.id, null, 'ban', reason);
        await sendLogToGuild(guild, client, makeEmbed('warning', 'User banned', `<@${author.id}> banned by AutoMod`, [{ name: 'Reason', value: reason, inline: false }]), author.id);
      } catch (e) {}
    } else {
      // Unknown action: ignore
    }
  }
}

// Fallback: nsfw stub analysis for attachments (if Vision not configured)
function nsfwStubAnalysis(url) {
  const token = (url || '').toLowerCase();
  const isNsfw = token.includes('nsfw') || token.includes('adult') || token.includes('porn') || token.includes('xxx');
  return { nsfw: isNsfw, score: isNsfw ? 0.95 : 0.02, adult: isNsfw ? 'VERY_LIKELY' : 'VERY_UNLIKELY' };
}

// ------------ Slash commands definitions (same set as Python cog) ------------
/**
 * Commands:
 *  /automod add_trigger name trigger_type pattern action threshold
 *  /automod remove_trigger rule_id pattern_or_name
 *  /automod list_triggers
 *  /automod config subcommand value
 *  /automod test kind sample
 *
 * Each command uses ephemeral replies for safety.
 */

const automodCommand = new SlashCommandBuilder()
  .setName('automod')
  .setDescription('AutoMod management and test commands (non-AI)')
  .addSubcommand(sc => sc
    .setName('add_trigger')
    .setDescription('Add an AutoMod trigger')
    .addStringOption(o => o.setName('name').setDescription('Rule name (human readable)').setRequired(true))
    .addStringOption(o => o.setName('trigger_type').setDescription('Type: keyword|mentions_excessive|invite|spam|regex').setRequired(true))
    .addStringOption(o => o.setName('pattern').setDescription('Keywords (comma-separated) or regex pattern').setRequired(false))
    .addStringOption(o => o.setName('action').setDescription('Action: delete|warn|temp_mute:seconds|kick|ban or combinations using +').setRequired(true))
    .addIntegerOption(o => o.setName('threshold').setDescription('Optional threshold for mention/spam')))
  .addSubcommand(sc => sc
    .setName('remove_trigger')
    .setDescription('Remove a native AutoMod rule by ID, or remove a DB fallback trigger by pattern or name')
    .addStringOption(o => o.setName('rule_id').setDescription('Native rule ID (optional)'))
    .addStringOption(o => o.setName('pattern_or_name').setDescription('DB fallback trigger pattern or name (optional)')))
  .addSubcommand(sc => sc
    .setName('list_triggers')
    .setDescription('List native AutoMod rules (if supported) or DB-stored fallback triggers'))
  .addSubcommand(sc => sc
    .setName('config')
    .setDescription('View or update automod configuration for this guild')
    .addStringOption(o => o.setName('subcommand').setDescription("show | set_log | add_mod_role | remove_mod_role | add_trusted | remove_trusted | set_banned_words").setRequired(true))
    .addStringOption(o => o.setName('value').setDescription('Value for subcommand (role mention/id, channel mention/id, comma-separated list, etc.)')))
  .addSubcommand(sc => sc
    .setName('test')
    .setDescription('Simulate automod checks: profanity|spam|link|nsfw|language')
    .addStringOption(o => o.setName('kind').setDescription('profanity|spam|link|nsfw|language').setRequired(true))
    .addStringOption(o => o.setName('sample').setDescription('Text or URL to test with')));

/**
 * Registers commands application-wide or per-guild if provided in options.
 * This simplistic registration uses the client's application and registers a single
 * top-level slash command with multiple subcommands (group style).
 */
async function registerCommands(client) {
  if (!client.application || !client.application.owner) {
    // must wait until ready
    return;
  }
  const rest = new REST({ version: '10' }).setToken(process.env.BOT_TOKEN);
  try {
    // Register global command (could be heavy to update; in production prefer guild-based during dev)
    await rest.put(Routes.applicationCommands(client.user.id), { body: [automodCommand.toJSON()] });
    console.log('AutoMod slash command registered globally.');
  } catch (e) {
    console.error('Failed to register slash commands', e);
  }
}

// ------------ Command handlers ------------
async function handleInteractionCreate(interaction) {
  if (!interaction.isChatInputCommand()) return;
  if (interaction.commandName !== 'automod') return;

  await interaction.deferReply({ ephemeral: true });
  const sub = interaction.options.getSubcommand();

  const guild = interaction.guild;
  if (!guild) {
    await interaction.editReply({ embeds: [makeEmbed('error', 'Guild required', 'This command must be used in a guild.')] });
    return;
  }

  const member = interaction.member;
  // Helper: check moderator
  async function isModerator(member) {
    const cfg = await getGuildConfig(guild.id);
    const modRoles = cfg.modRoleIds || [];
    if (guild.ownerId === member.user.id) return true;
    if (member.permissions.has(PermissionsBitField.Flags.Administrator)) return true;
    for (const r of member.roles.cache.values()) {
      if (modRoles.includes(r.id)) return true;
    }
    return false;
  }

  if (sub === 'add_trigger') {
    if (!await isModerator(member)) {
      await interaction.editReply({ embeds: [makeEmbed('error', 'Permission denied', 'You must be a configured moderator or guild admin/owner to add triggers.')] });
      return;
    }
    const name = interaction.options.getString('name');
    const trigger_type = interaction.options.getString('trigger_type');
    const pattern = interaction.options.getString('pattern') || '';
    const action = interaction.options.getString('action') || 'warn';
    const threshold = interaction.options.getInteger('threshold') || null;

    // Attempt native automod creation is runtime-dependent; we fallback to DB storage as this module doesn't manage native automod APIs.
    await ensureGuildCfg(guild.id);
    const cfg = await getGuildConfig(guild.id);
    const trigs = cfg.automodTriggers || [];
    trigs.push({ name, trigger_type, pattern, action, metadata: { threshold } });
    cfg.automodTriggers = trigs;
    await setGuildConfig(guild.id, cfg);
    await addInfraction(guild.id, 0, member.user.id, 'config', `add_trigger ${name}`);
    await interaction.editReply({ embeds: [makeEmbed('success', 'Fallback trigger stored', `Stored trigger **${name}** as DB fallback.`)] });
    // log
    await sendLogToGuild(guild, interaction.client, makeEmbed('info', 'Fallback AutoMod trigger stored', `Trigger '${name}' stored in DB fallback.`, [{ name: 'Type', value: trigger_type, inline: true }, { name: 'Pattern', value: pattern || '(none)', inline: true }, { name: 'Action', value: action, inline: true }]), null);
    return;
  }

  if (sub === 'remove_trigger') {
    if (!await isModerator(member)) {
      await interaction.editReply({ embeds: [makeEmbed('error', 'Permission denied', 'You must be a configured moderator or admin to remove triggers.')] });
      return;
    }
    const ruleId = interaction.options.getString('rule_id');
    const patternOrName = interaction.options.getString('pattern_or_name');

    if (ruleId) {
      // We don't manage native rules here; inform user that native delete may require Discord API usage.
      await interaction.editReply({ embeds: [makeEmbed('error', 'Native deletion unsupported', 'Deleting native AutoMod rules is not supported by this module. Remove DB fallback triggers instead.')] });
      return;
    }
    if (patternOrName) {
      await ensureGuildCfg(guild.id);
      const cfg = await getGuildConfig(guild.id);
      const trigs = cfg.automodTriggers || [];
      const newTrigs = trigs.filter(t => !((t.pattern || '').toLowerCase().includes(patternOrName.toLowerCase()) || (t.name || '').toLowerCase().includes(patternOrName.toLowerCase())));
      const removed = trigs.length - newTrigs.length;
      cfg.automodTriggers = newTrigs;
      await setGuildConfig(guild.id, cfg);
      await interaction.editReply({ embeds: [makeEmbed('success', 'Fallback triggers updated', `Removed ${removed} fallback trigger(s) matching \`${patternOrName}\`.`)] });
      await sendLogToGuild(guild, interaction.client, makeEmbed('info', 'Fallback triggers removed', `${removed} fallback trigger(s) removed by ${interaction.user.tag}`), null);
      return;
    }
    await interaction.editReply({ embeds: [makeEmbed('error', 'Missing arguments', 'Provide either rule_id (native) or pattern_or_name (fallback) to remove.')] });
    return;
  }

  if (sub === 'list_triggers') {
    await ensureGuildCfg(guild.id);
    const cfg = await getGuildConfig(guild.id);
    const trigs = cfg.automodTriggers || [];
    if (!trigs.length) {
      await interaction.editReply({ embeds: [makeEmbed('info', 'Triggers', 'No native rules and no DB fallback triggers found.')] });
      return;
    }
    const text = trigs.map(t => `• **${t.name || '(no name)'}** • \`${t.trigger_type}\` • \`${t.pattern || ''}\` -> \`${t.action}\``).join('\n');
    await interaction.editReply({ embeds: [makeEmbed('info', 'DB fallback triggers', text)] });
    return;
  }

  if (sub === 'config') {
    if (!await isModerator(member)) {
      await interaction.editReply({ embeds: [makeEmbed('error', 'Permission denied', 'You must be a configured moderator or guild admin to manage the automod config.')] });
      return;
    }
    const subcommand = interaction.options.getString('subcommand');
    const value = interaction.options.getString('value');

    await ensureGuildCfg(guild.id);
    const cfg = await getGuildConfig(guild.id);

    const s = (subcommand || '').toLowerCase();
    if (s === 'show') {
      const fields = [
        { name: 'Log Channel', value: String(cfg.logChannelId || 'None'), inline: true },
        { name: 'Mod Roles', value: (cfg.modRoleIds || []).map(x => `<@&${x}>`).join(', ') || 'None', inline: true },
        { name: 'Trusted Roles', value: (cfg.trustedRoleIds || []).map(x => `<@&${x}>`).join(', ') || 'None', inline: true },
        { name: 'Banned words', value: (cfg.bannedWords || []).slice(0, 20).join(', ') || 'None', inline: false },
        { name: 'Spam threshold', value: JSON.stringify(cfg.spamThreshold || {}), inline: true },
        { name: 'Links whitelist', value: (cfg.linksWhitelist || []).slice(0, 10).join(', ') || 'None', inline: false },
        { name: 'Links blacklist', value: (cfg.linksBlacklist || []).slice(0, 10).join(', ') || 'None', inline: false },
      ];
      await interaction.editReply({ embeds: [makeEmbed('info', 'AutoMod Configuration', 'Current configuration snapshot', fields)] });
      return;
    }

    if (s === 'set_log') {
      if (!value) { await interaction.editReply({ embeds: [makeEmbed('error', 'Missing value', 'Provide a channel mention or channel ID.')] }); return; }
      let chId = null;
      const m = value.match(/<#(\d+)>/);
      if (m) chId = m[1];
      else if (!isNaN(Number(value))) chId = value;
      if (!chId) { await interaction.editReply({ embeds: [makeEmbed('error', 'Invalid channel', 'Could not parse channel id.')] }); return; }
      cfg.logChannelId = chId;
      await setGuildConfig(guild.id, cfg);
      await interaction.editReply({ embeds: [makeEmbed('success', 'Log channel set', `AutoMod logs will be sent to <#${chId}> (if bot has access).`)] });
      return;
    }

    if (s === 'add_mod_role' || s === 'remove_mod_role') {
      if (!value) { await interaction.editReply({ embeds: [makeEmbed('error', 'Missing value', 'Provide a role mention or role ID.')] }); return; }
      let roleId = null;
      const m = value.match(/<@&(\d+)>/);
      if (m) roleId = m[1];
      else if (!isNaN(Number(value))) roleId = value;
      if (!roleId) { await interaction.editReply({ embeds: [makeEmbed('error', 'Invalid role', 'Could not parse role id.')] }); return; }
      const modRoles = cfg.modRoleIds || [];
      if (s === 'add_mod_role') {
        if (!modRoles.includes(roleId)) { modRoles.push(roleId); cfg.modRoleIds = modRoles; await setGuildConfig(guild.id, cfg); }
        await interaction.editReply({ embeds: [makeEmbed('success', 'Mod role updated', `Role <@&${roleId}> added to mod roles.`)] });
      } else {
        cfg.modRoleIds = modRoles.filter(r => r !== roleId);
        await setGuildConfig(guild.id, cfg);
        await interaction.editReply({ embeds: [makeEmbed('success', 'Mod role removed', `Role <@&${roleId}> removed from mod roles.`)] });
      }
      return;
    }

    if (s === 'add_trusted' || s === 'remove_trusted') {
      if (!value) { await interaction.editReply({ embeds: [makeEmbed('error', 'Missing value', 'Provide a role mention or role ID.')] }); return; }
      let roleId = null;
      const m = value.match(/<@&(\d+)>/);
      if (m) roleId = m[1];
      else if (!isNaN(Number(value))) roleId = value;
      if (!roleId) { await interaction.editReply({ embeds: [makeEmbed('error', 'Invalid role', 'Could not parse role id.')] }); return; }
      const trusted = cfg.trustedRoleIds || [];
      if (s === 'add_trusted') {
        if (!trusted.includes(roleId)) { trusted.push(roleId); cfg.trustedRoleIds = trusted; await setGuildConfig(guild.id, cfg); }
        await interaction.editReply({ embeds: [makeEmbed('success', 'Trusted role updated', `Role <@&${roleId}> added to trusted roles.`)] });
      } else {
        cfg.trustedRoleIds = trusted.filter(r => r !== roleId); await setGuildConfig(guild.id, cfg);
        await interaction.editReply({ embeds: [makeEmbed('success', 'Trusted role removed', `Role <@&${roleId}> removed from trusted roles.`)] });
      }
      return;
    }

    if (s === 'set_banned_words') {
      if (value == null) { await interaction.editReply({ embeds: [makeEmbed('error', 'Missing value', 'Provide a comma-separated list or "none".')] }); return; }
      if (value.trim().toLowerCase() === 'none') cfg.bannedWords = [];
      else cfg.bannedWords = value.split(',').map(w => w.trim()).filter(Boolean);
      await setGuildConfig(guild.id, cfg);
      await interaction.editReply({ embeds: [makeEmbed('success', 'Banned words updated', `New banned words: ${(cfg.bannedWords || []).join(', ') || 'None'}`)] });
      return;
    }

    await interaction.editReply({ embeds: [makeEmbed('error', 'Unknown subcommand', 'Supported: show, set_log, add_mod_role, remove_mod_role, add_trusted, remove_trusted, set_banned_words')] });
    return;
  }

  if (sub === 'test') {
    const kind = (interaction.options.getString('kind') || '').toLowerCase();
    const sample = interaction.options.getString('sample') || '';
    await ensureGuildCfg(guild.id);
    const cfg = await getGuildConfig(guild.id);

    if (kind === 'profanity') {
      if (!sample) { await interaction.editReply({ embeds: [makeEmbed('error', 'Missing sample', 'Provide sample text to test profanity.')] }); return; }
      const found = (cfg.bannedWords || []).filter(w => sample.toLowerCase().includes(w.toLowerCase()));
      if (found.length) {
        await interaction.editReply({ embeds: [makeEmbed('warning', 'Profanity test — would trigger', `Found banned words: ${found.join(', ')}\nAction: delete & warn`)] });
      } else {
        await interaction.editReply({ embeds: [makeEmbed('success', 'Profanity test — clean', 'No banned words detected')] });
      }
      return;
    }

    if (kind === 'spam') {
      const thr = cfg.spamThreshold || {};
      await interaction.editReply({ embeds: [makeEmbed('info', 'Spam threshold', `${thr.messages} messages in ${thr.seconds} seconds`)] });
      return;
    }

    if (kind === 'link') {
      if (!sample) { await interaction.editReply({ embeds: [makeEmbed('error', 'Missing sample', 'Provide a sample URL to test.')] }); return; }
      const domains = extractDomainsFromText(sample);
      const bl = cfg.linksBlacklist || [];
      const wl = cfg.linksWhitelist || [];
      const reasons = [];
      for (const d of domains) {
        if (domainInPatterns(d, bl)) reasons.push(`${d} — blacklisted`);
        else if (wl && wl.length && !domainInPatterns(d, wl)) reasons.push(`${d} — not whitelisted`);
        else reasons.push(`${d} — allowed`);
      }
      await interaction.editReply({ embeds: [makeEmbed('info', 'Link test', reasons.join('\n') || 'No links detected')] });
      return;
    }

    if (kind === 'nsfw') {
      if (!sample) { await interaction.editReply({ embeds: [makeEmbed('error', 'Missing URL', 'Provide an image URL to test.')] }); return; }
      const base64 = await fetchAttachmentAsBase64(sample).catch(() => null);
      const res = base64 ? await analyzeImageSafeSearchBase64(base64) : nsfwStubAnalysis(sample);
      if (!res) {
        await interaction.editReply({ embeds: [makeEmbed('error', 'Vision check failed', 'Could not analyze image (Vision key missing or API error).')] });
        return;
      }
      const flagged = (Object.entries(res).map(([k, v]) => `${k}: ${v}`)).join('\n');
      await interaction.editReply({ embeds: [makeEmbed('info', 'NSFW test (Vision)', flagged)] });
      return;
    }

    if (kind === 'language') {
      if (!sample) { await interaction.editReply({ embeds: [makeEmbed('error', 'Missing sample', 'Provide sample text to test language detection.')] }); return; }
      const detected = detectLanguageStub(sample);
      await interaction.editReply({ embeds: [makeEmbed('info', 'Language test', `Detected language: \`${detected}\``)] });
      return;
    }

    await interaction.editReply({ embeds: [makeEmbed('error', 'Unknown test kind', 'Supported: profanity, spam, link, nsfw, language')] });
    return;
  }
}

// ------------ Public setup function (call from your loader) ------------
/**
 * Call setup(client)
 * - registers slash commands (global)
 * - registers listeners: messageCreate, interactionCreate
 * - starts unmute watcher
 */
async function setup(client) {
  if (!client) throw new Error('Client required');
  await initDb();

  client.on('messageCreate', msg => {
    // run pipeline asynchronously but don't await (best-effort)
    onMessageCreate(client, msg).catch(err => console.error('onMessageCreate error', err));
  });

  client.on('interactionCreate', async interaction => {
    // handle moderator buttons:
    if (interaction.isButton && interaction.isButton()) {
      await handleModeratorButton(interaction).catch(e => console.error('button handler error', e));
      return;
    }
    // handle slash commands
    try {
      await handleInteractionCreate(interaction);
    } catch (e) {
      console.error('interaction handler error', e);
      if (interaction.deferred || interaction.replied) {
        try { await interaction.editReply({ content: 'Error processing command (see logs).' }); } catch (e) {}
      } else {
        try { await interaction.reply({ content: 'Error processing command (see logs).', ephemeral: true }); } catch (e) {}
      }
    }
  });

  client.once('ready', async () => {
    console.log(`AutoMod module loaded — bot ready as ${client.user.tag}`);
    // Register slash commands (global)
    try { await registerCommands(client); } catch (e) { console.warn('Failed to register commands', e); }
    // Start unmute watcher
    await startUnmuteWatcher(client);
  });
}

module.exports = { setup }
