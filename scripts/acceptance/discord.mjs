import {
  AuditLogEvent,
  Client,
  GatewayIntentBits,
  PermissionFlagsBits,
} from "discord.js";

const token = process.env.DISCORD_TOKEN?.trim();
const guildId = process.env.GUILD_ID?.trim();
const expectedInviterId = process.env.DISCORD_TEST_INVITER_ID?.trim() || null;

if (!token || !guildId || !/^\d{17,20}$/.test(guildId)) {
  throw new Error("DISCORD_TOKEN and a valid GUILD_ID are required for live Discord acceptance.");
}

const client = new Client({ intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMembers] });
try {
  await client.login(token);
  await new Promise((resolve, reject) => {
    if (client.isReady()) return resolve();
    const timer = setTimeout(() => reject(new Error("Discord client did not become ready within 30 seconds.")), 30_000);
    client.once("ready", () => { clearTimeout(timer); resolve(); });
    client.once("error", error => { clearTimeout(timer); reject(error); });
  });

  const guild = await client.guilds.fetch(guildId);
  const member = await guild.members.fetchMe();
  if (!member.permissions.has(PermissionFlagsBits.ViewAuditLog)) {
    throw new Error("The bot lacks View Audit Log in the acceptance guild.");
  }
  if (!member.permissions.has(PermissionFlagsBits.ManageRoles)) {
    throw new Error("The bot lacks Manage Roles in the acceptance guild; Custom Roles cannot be fully exercised.");
  }

  const audit = await guild.fetchAuditLogs({ type: AuditLogEvent.BotAdd, limit: 50 });
  const botInvite = audit.entries.find(entry => entry.targetId === client.user.id) ?? null;
  if (expectedInviterId && botInvite?.executorId !== expectedInviterId) {
    throw new Error("The latest matching bot-add audit entry does not match DISCORD_TEST_INVITER_ID.");
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

  process.stdout.write(JSON.stringify({
    ok: true,
    guildId: guild.id,
    botUserId: client.user.id,
    auditLogReadable: true,
    botAddAuditEntryFound: Boolean(botInvite),
    inviterMatched: expectedInviterId ? botInvite?.executorId === expectedInviterId : null,
    manageRoles: true,
    globalCommandsVerified: requiredCommands.length,
  }) + "\n");
} finally {
  client.destroy();
}
