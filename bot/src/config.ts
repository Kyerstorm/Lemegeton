export interface BotConfig {
  discordToken: string;
  applicationId: string;
  guildId?: string;
  anilistApiUrl: string;
  anilistTimeoutMs: number;
}

function requiredValue(env: NodeJS.ProcessEnv, key: string): string {
  const value = env[key]?.trim();
  if (!value) {
    throw new Error(`Missing required environment variable: ${key}`);
  }
  return value;
}

function optionalSnowflake(value: string | undefined, key: string): string | undefined {
  const normalized = value?.trim();
  if (!normalized) return undefined;
  if (!/^\d{17,20}$/.test(normalized)) {
    throw new Error(`${key} must be a valid Discord snowflake.`);
  }
  return normalized;
}

function positiveInteger(value: string | undefined, fallback: number, key: string): number {
  if (!value?.trim()) return fallback;
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < 1) {
    throw new Error(`${key} must be a positive integer.`);
  }
  return parsed;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): BotConfig {
  const discordToken = requiredValue(env, "DISCORD_TOKEN");
  const applicationId = env.DISCORD_CLIENT_ID?.trim() || env.BOT_ID?.trim();
  if (!applicationId) {
    throw new Error("Missing required environment variable: BOT_ID (or DISCORD_CLIENT_ID)");
  }

  const anilistApiUrl = env.ANILIST_API_URL?.trim() || "https://graphql.anilist.co";
  const parsedApiUrl = new URL(anilistApiUrl);
  if (parsedApiUrl.protocol !== "https:" && parsedApiUrl.hostname !== "localhost" && parsedApiUrl.hostname !== "127.0.0.1") {
    throw new Error("ANILIST_API_URL must use HTTPS (HTTP is allowed only for localhost development).");
  }

  const normalizedApplicationId = optionalSnowflake(applicationId, "BOT_ID / DISCORD_CLIENT_ID");
  const guildId = optionalSnowflake(env.DISCORD_GUILD_ID, "DISCORD_GUILD_ID");
  if (!normalizedApplicationId) {
    throw new Error("Missing required environment variable: BOT_ID (or DISCORD_CLIENT_ID)");
  }

  return {
    discordToken,
    applicationId: normalizedApplicationId,
    ...(guildId ? { guildId } : {}),
    anilistApiUrl: parsedApiUrl.toString(),
    anilistTimeoutMs: positiveInteger(env.ANILIST_API_TIMEOUT, 10, "ANILIST_API_TIMEOUT") * 1_000,
  };
}
