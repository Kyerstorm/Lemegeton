import {
  AuditLogEvent,
  ChannelType,
  Client,
  GatewayIntentBits,
  PermissionFlagsBits,
} from "discord.js";

const token = process.env.DISCORD_TOKEN?.trim();
const guildId = process.env.GUILD_ID?.trim();
const expectedInviterId = process.env.DISCORD_TEST_INVITER_ID?.trim();
const channelId = process.env.DISCORD_TEST_CHANNEL_ID?.trim();
const moderatorGuildId = process.env.DISCORD_TEST_MODERATOR_GUILD_ID?.trim() || null;

if (!token || !/^\d{17,20}$/.test(guildId ?? "")
  || !/^\d{17,20}$/.test(expectedInviterId ?? "")
  || !/^\d{17,20}$/.test(channelId ?? "")) {
  throw new Error("DISCORD_TOKEN, GUILD_ID, DISCORD_TEST_INVITER_ID and DISCORD_TEST_CHANNEL_ID are required.");
}

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMembers,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent,
  ],
});

try {
  await client.login(token);
  await new Promise((resolve, reject) => {
    if (client.isReady()) return resolve();
    const timer = setTimeout(() => reject(new Error("Discord client did not become ready within 30 seconds.")), 30_000);
    client.once("ready", () => { clearTimeout(timer); resolve(); });
    client.once("error", error => { clearTimeout(timer); reject(error); });
  });

  const guild = await client.guilds.fetch(guildId);
  const botMember = await guild.members.fetchMe();
  if (!botMember.permissions.has(PermissionFlagsBits.ViewAuditLog)) {
    throw new Error("The bot lacks View Audit Log in the acceptance guild.");
  }
  if (!botMember.permissions.has(PermissionFlagsBits.ManageRoles)) {
    throw new Error("The bot lacks Manage Roles in the acceptance guild; Custom Roles cannot be fully exercised.");
  }

  const inviter = await guild.members.fetch(expectedInviterId);
  if (!inviter.permissions.has(PermissionFlagsBits.ManageGuild)
    && !inviter.permissions.has(PermissionFlagsBits.Administrator)) {
    throw new Error("The recorded inviter no longer has Manage Server or Administrator permission for retention choices.");
  }

  const audit = await guild.fetchAuditLogs({ type: AuditLogEvent.BotAdd, limit: 100 });
  const botInvite = audit.entries.find(entry => entry.targetId === client.user.id) ?? null;
  if (!botInvite) throw new Error("The bot-add audit entry is unavailable in the acceptance guild.");
  if (botInvite.executorId !== expectedInviterId) {
    throw new Error("The latest matching bot-add audit entry does not match DISCORD_TEST_INVITER_ID.");
  }

  const channel = await guild.channels.fetch(channelId);
  if (!channel || (channel.type !== ChannelType.GuildText && channel.type !== ChannelType.GuildAnnouncement)) {
    throw new Error("DISCORD_TEST_CHANNEL_ID must identify a text or announcement channel in the acceptance guild.");
  }
  const channelPermissions = channel.permissionsFor(botMember);
  const channelRequirements = [
    ["ViewChannel", PermissionFlagsBits.ViewChannel],
    ["SendMessages", PermissionFlagsBits.SendMessages],
    ["ReadMessageHistory", PermissionFlagsBits.ReadMessageHistory],
    ["AttachFiles", PermissionFlagsBits.AttachFiles],
    ["CreatePublicThreads", PermissionFlagsBits.CreatePublicThreads],
    ["SendMessagesInThreads", PermissionFlagsBits.SendMessagesInThreads],
  ];
  const missingChannelPermissions = channelRequirements
    .filter(([, permission]) => !channelPermissions?.has(permission))
    .map(([name]) => name);
  if (missingChannelPermissions.length) {
    throw new Error("The configured test channel is missing bot permissions: " + missingChannelPermissions.join(", "));
  }

  await client.application.fetch();
  const globalCommands = await client.application.commands.fetch();
  const requiredCommands = [
    "discover", "archive", "community", "play", "profile", "custom-role", "settings",
    "help", "privacy", "feedback",
  ];
  const missingCommands = requiredCommands.filter(name => !globalCommands.has(name));
  if (missingCommands.length) {
    throw new Error("Missing globally deployed commands: " + missingCommands.join(", "));
  }

  let moderatorCommandsVerified = 0;
  if (moderatorGuildId) {
    if (!/^\d{17,20}$/.test(moderatorGuildId)) throw new Error("DISCORD_TEST_MODERATOR_GUILD_ID is invalid.");
    const moderatorGuild = await client.guilds.fetch(moderatorGuildId);
    const guildCommands = await moderatorGuild.commands.fetch();
    const requiredModeratorCommands = ["log", "moderators", "planned", "adminlogin", "convertlinks"];
    const missing = requiredModeratorCommands.filter(name => !guildCommands.has(name));
    if (missing.length) throw new Error("Missing moderator-server commands: " + missing.join(", "));
    moderatorCommandsVerified = requiredModeratorCommands.length;
  }

  process.stdout.write(JSON.stringify({
    ok: true,
    guildId: guild.id,
    botUserId: client.user.id,
    inviterId: botInvite.executorId,
    inviterCanConfigureRetention: true,
    botAddAuditLogReadable: true,
    channelId: channel.id,
    channelPermissionsVerified: channelRequirements.map(([name]) => name),
    manageRoles: true,
    globalCommandsVerified: requiredCommands.length,
    moderatorCommandsVerified,
  }) + "\n");
} finally {
  client.destroy();
}
