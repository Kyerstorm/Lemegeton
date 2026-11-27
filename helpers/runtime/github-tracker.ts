import {
  ChannelType,
  EmbedBuilder,
  PermissionFlagsBits,
  type Client,
  type TextChannel,
} from "discord.js";
import { query, queryOne } from "../../src/utility/database/libsql/database.js";
import type { BotConfig } from "./config.js";
import { logger } from "./logger.js";

const API_URL = "https://api.github.com";
const HISTORY_LIMIT = 100;
const STATS_LOOKUP_LIMIT = 20;
const STATS_CONCURRENCY = 4;
const REQUEST_TIMEOUT_MS = 15_000;
const DISPLAY_COMMIT_LIMIT = 12;

export class GitHubTrackerError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "GitHubTrackerError";
  }
}

export interface GitHubCommit {
  sha: string;
  url: string;
  message: string;
  author: string;
  committedAt: string | null;
}

export interface GitHubCommitStats {
  sha: string;
  additions: number;
  deletions: number;
  files: string[];
}

export interface GitHubActivitySummary {
  commits: GitHubCommit[];
  additions: number;
  deletions: number;
  filesChanged: number;
  statsFor: number;
  windowLabel: string;
}

export interface GitHubTrackerState {
  last_sha: string | null;
  last_checked_at: Date | string | null;
  last_error: string | null;
}

export type GitHubCheckResult =
  | { kind: "initialised"; headSha: string | null }
  | { kind: "no-commits" }
  | { kind: "history-reset"; headSha: string }
  | { kind: "updates"; summary: GitHubActivitySummary; published: boolean };

interface GitHubApiCommit {
  sha?: unknown;
  html_url?: unknown;
  author?: { login?: unknown } | null;
  commit?: {
    message?: unknown;
    author?: { name?: unknown; date?: unknown } | null;
    committer?: { date?: unknown } | null;
  } | null;
}

interface GitHubApiCommitDetails {
  stats?: { additions?: unknown; deletions?: unknown } | null;
  files?: Array<{ filename?: unknown }> | null;
}

let checking = false;
let timer: ReturnType<typeof setInterval> | null = null;
let activeCycle: Promise<void> | null = null;

function apiHeaders(config: BotConfig): HeadersInit {
  return {
    Accept: "application/vnd.github+json",
    "User-Agent": "Lemegeton-Discord-Bot",
    "X-GitHub-Api-Version": "2022-11-28",
    ...(config.githubToken ? { Authorization: "Bearer " + config.githubToken } : {}),
  };
}

async function requestGitHub<T>(url: string, config: BotConfig): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {
      headers: apiHeaders(config),
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch {
    throw new GitHubTrackerError("GitHub could not be reached. Check the connection and try again.");
  }
  if (!response.ok) {
    if ((response.status === 403 || response.status === 429)
      && response.headers.get("x-ratelimit-remaining") === "0") {
      const reset = Number(response.headers.get("x-ratelimit-reset"));
      const resetText = Number.isFinite(reset) && reset > 0
        ? " The limit resets <t:" + Math.floor(reset) + ":R>."
        : "";
      throw new GitHubTrackerError("GitHub's API rate limit has been reached." + resetText);
    }
    if (response.status === 404) {
      throw new GitHubTrackerError("The configured GitHub repository or branch could not be found.");
    }
    if (response.status === 401) {
      throw new GitHubTrackerError("GitHub rejected the configured API token.");
    }
    throw new GitHubTrackerError("GitHub returned HTTP " + response.status + ".");
  }
  try {
    return await response.json() as T;
  } catch {
    throw new GitHubTrackerError("GitHub returned an unreadable response.");
  }
}

function repositorySegments(config: BotConfig): [string, string] {
  const [owner, repository] = config.githubRepository.split("/");
  if (!owner || !repository) throw new GitHubTrackerError("GITHUB_REPO must use owner/repository format.");
  return [owner, repository];
}

function commitsUrl(config: BotConfig, limit: number): string {
  const [owner, repository] = repositorySegments(config);
  const query = new URLSearchParams({ sha: config.githubBranch, per_page: String(limit) });
  return API_URL + "/repos/" + encodeURIComponent(owner) + "/" + encodeURIComponent(repository) + "/commits?" + query;
}

function toGitHubCommit(raw: GitHubApiCommit, config: BotConfig): GitHubCommit | null {
  if (typeof raw.sha !== "string" || !/^[a-f0-9]{40,64}$/i.test(raw.sha)) return null;
  const rawMessage = typeof raw.commit?.message === "string" ? raw.commit.message : "";
  const message = rawMessage.split("\n", 1)[0]?.trim() ?? "";
  const author = typeof raw.author?.login === "string"
    ? raw.author.login
    : typeof raw.commit?.author?.name === "string" ? raw.commit.author.name : "Unknown";
  const committedAt = typeof raw.commit?.committer?.date === "string"
    ? raw.commit.committer.date
    : typeof raw.commit?.author?.date === "string" ? raw.commit.author.date : null;
  return {
    sha: raw.sha,
    url: "https://github.com/" + config.githubRepository + "/commit/" + raw.sha,
    message: message || "Untitled commit",
    author,
    committedAt,
  };
}

export async function fetchRecentGitHubCommits(config: BotConfig, count: number): Promise<GitHubCommit[]> {
  const result = await requestGitHub<unknown>(commitsUrl(config, Math.min(20, Math.max(1, count))), config);
  if (!Array.isArray(result)) throw new GitHubTrackerError("GitHub returned an invalid commit list.");
  return result
    .map(item => toGitHubCommit(item as GitHubApiCommit, config))
    .filter((item): item is GitHubCommit => item !== null);
}

async function fetchCommitStats(
  commits: GitHubCommit[],
  config: BotConfig,
): Promise<GitHubCommitStats[]> {
  const batch = commits.slice(-STATS_LOOKUP_LIMIT);
  const results: GitHubCommitStats[] = [];
  let cursor = 0;
  const worker = async (): Promise<void> => {
    while (cursor < batch.length) {
      const commit = batch[cursor++];
      if (!commit) return;
      try {
        const [owner, repository] = repositorySegments(config);
        const details = await requestGitHub<GitHubApiCommitDetails>(
          API_URL + "/repos/" + encodeURIComponent(owner) + "/" + encodeURIComponent(repository)
            + "/commits/" + encodeURIComponent(commit.sha),
          config,
        );
        if (!details.stats) continue;
        results.push({
          sha: commit.sha,
          additions: Number.isSafeInteger(details.stats.additions) ? Number(details.stats.additions) : 0,
          deletions: Number.isSafeInteger(details.stats.deletions) ? Number(details.stats.deletions) : 0,
          files: Array.isArray(details.files)
            ? details.files.flatMap(file => typeof file.filename === "string" ? [file.filename] : [])
            : [],
        });
      } catch (error) {
        logger.warn("GitHub commit statistics could not be retrieved", {
          sha: commit.sha.slice(0, 7),
          reason: error instanceof Error ? error.message : "Unknown error",
        });
      }
    }
  };
  await Promise.all(Array.from({ length: Math.min(STATS_CONCURRENCY, batch.length) }, worker));
  return results;
}

export async function createRecentGitHubActivity(
  config: BotConfig,
  count: number,
): Promise<GitHubActivitySummary> {
  const commits = await fetchRecentGitHubCommits(config, count);
  const stats = await fetchCommitStats(commits, config);
  return summarizeGitHubActivity([...commits].reverse(), stats);
}

function activityWindow(commits: GitHubCommit[]): string {
  if (commits.length === 1) return "single commit";
  const dates = commits.map(commit => Date.parse(commit.committedAt ?? "")).filter(Number.isFinite);
  if (dates.length < 2) return "grouped update";
  const minutes = Math.max(1, Math.round((Math.max(...dates) - Math.min(...dates)) / 60_000));
  return minutes + " min window";
}

export function summarizeGitHubActivity(
  commits: GitHubCommit[],
  stats: GitHubCommitStats[],
): GitHubActivitySummary {
  const files = new Set<string>();
  let additions = 0;
  let deletions = 0;
  for (const stat of stats) {
    additions += stat.additions;
    deletions += stat.deletions;
    for (const file of stat.files) files.add(file);
  }
  return {
    commits,
    additions,
    deletions,
    filesChanged: files.size,
    statsFor: stats.length,
    windowLabel: activityWindow(commits),
  };
}

function safeMarkdown(value: string, limit: number): string {
  return value
    .replace(/@everyone/gi, "@\u200beveryone")
    .replace(/@here/gi, "@\u200bhere")
    .replace(/[\r\n\t]+/g, " ")
    .replace(/([\\`*_{}\[\]()#+\-.!|>~])/g, "\\$1")
    .slice(0, limit);
}

export function buildGitHubActivityEmbed(
  summary: GitHubActivitySummary,
  repository: string,
  branch: string,
): EmbedBuilder {
  const count = summary.commits.length;
  const statsCoverage = summary.statsFor + "/" + count;
  const complete = summary.statsFor === count;
  const changes = (value: number) => complete ? value.toLocaleString("en-US") : value.toLocaleString("en-US") + " · " + statsCoverage;
  const fileCount = complete ? summary.filesChanged.toLocaleString("en-US") : summary.filesChanged.toLocaleString("en-US") + " observed";
  const lines = summary.commits.slice(-DISPLAY_COMMIT_LIMIT).reverse().map(commit =>
    "[\x60" + commit.sha.slice(0, 7) + "\x60](" + commit.url + ") " +
    safeMarkdown(commit.message, 105) + " · " + safeMarkdown(commit.author, 45),
  );
  if (count > DISPLAY_COMMIT_LIMIT) lines.push("+" + (count - DISPLAY_COMMIT_LIMIT) + " more commits");
  const newestDate = Math.max(...summary.commits.map(commit => Date.parse(commit.committedAt ?? "")).filter(Number.isFinite));
  const embed = new EmbedBuilder()
    .setColor(0x24292f)
    .setTitle("GitHub activity")
    .setURL("https://github.com/" + repository + "/commits/" + encodeURIComponent(branch))
    .setDescription(
      "**" + count.toLocaleString("en-US") + " commit" + (count === 1 ? "" : "s") + "** · " + summary.windowLabel
        + "\n\n" + lines.join("\n"),
    )
    .addFields(
      { name: "Lines added", value: complete || summary.statsFor ? "+" + changes(summary.additions) : "Unavailable", inline: true },
      { name: "Lines removed", value: complete || summary.statsFor ? "−" + changes(summary.deletions) : "Unavailable", inline: true },
      { name: "Distinct files", value: summary.statsFor ? fileCount : "Unavailable", inline: true },
    )
    .setFooter({ text: repository + " · " + branch + " · statistics " + statsCoverage + (complete ? "" : " (latest commits)") });
  if (Number.isFinite(newestDate)) embed.setTimestamp(new Date(newestDate));
  return embed;
}

export async function getGitHubTrackerState(config: BotConfig): Promise<GitHubTrackerState | null> {
  return queryOne<GitHubTrackerState>(
    "SELECT last_sha, last_checked_at, last_error FROM github_tracker_state WHERE repository = $1 AND branch = $2",
    [config.githubRepository, config.githubBranch],
  );
}

async function saveTrackerState(
  config: BotConfig,
  lastSha: string | null,
  lastError: string | null = null,
): Promise<void> {
  await query(
    `INSERT INTO github_tracker_state (repository, branch, last_sha, last_checked_at, last_error)
     VALUES ($1,$2,$3,NOW(),$4)
     ON CONFLICT (repository,branch) DO UPDATE SET
       last_sha=COALESCE(EXCLUDED.last_sha,github_tracker_state.last_sha),
       last_checked_at=NOW(),last_error=EXCLUDED.last_error`,
    [config.githubRepository, config.githubBranch, lastSha, lastError],
  );
}

async function publishActivity(
  client: Client,
  config: BotConfig,
  summary: GitHubActivitySummary,
): Promise<void> {
  if (!config.githubUpdateChannelId || !config.botModeratorGuildId) {
    throw new GitHubTrackerError("Automatic GitHub announcements are not configured.");
  }
  if (!client.user) throw new GitHubTrackerError("The bot is not ready to publish GitHub updates.");
  const fetched = await client.channels.fetch(config.githubUpdateChannelId).catch(() => null);
  if (!fetched || (fetched.type !== ChannelType.GuildText && fetched.type !== ChannelType.GuildAnnouncement)) {
    throw new GitHubTrackerError("The configured GitHub updates channel is unavailable.");
  }
  const channel = fetched as TextChannel;
  if (channel.guildId !== config.botModeratorGuildId) {
    throw new GitHubTrackerError("The GitHub updates channel must belong to the configured bot moderator server.");
  }
  const permissions = channel.permissionsFor(client.user);
  if (!permissions?.has([
    PermissionFlagsBits.ViewChannel,
    PermissionFlagsBits.SendMessages,
    PermissionFlagsBits.EmbedLinks,
  ])) {
    throw new GitHubTrackerError("The bot needs View Channel, Send Messages and Embed Links in the GitHub updates channel.");
  }
  await channel.send({ embeds: [buildGitHubActivityEmbed(summary, config.githubRepository, config.githubBranch)], allowedMentions: { parse: [] } });
}

async function fetchTrackingHistory(config: BotConfig): Promise<GitHubCommit[]> {
  const result = await requestGitHub<unknown>(commitsUrl(config, HISTORY_LIMIT), config);
  if (!Array.isArray(result)) throw new GitHubTrackerError("GitHub returned an invalid commit history.");
  return result
    .map(item => toGitHubCommit(item as GitHubApiCommit, config))
    .filter((item): item is GitHubCommit => item !== null);
}

export async function runGitHubCheck(
  client: Client,
  config: BotConfig,
  publish = Boolean(config.githubUpdateChannelId),
): Promise<GitHubCheckResult> {
  if (checking) throw new GitHubTrackerError("A GitHub check is already running. Try again shortly.");
  checking = true;
  try {
    const [state, history] = await Promise.all([
      getGitHubTrackerState(config),
      fetchTrackingHistory(config),
    ]);
    const head = history[0];
    if (!head) {
      await saveTrackerState(config, null);
      return { kind: "no-commits" };
    }
    if (!state?.last_sha) {
      await saveTrackerState(config, head.sha);
      return { kind: "initialised", headSha: head.sha };
    }
    const previousIndex = history.findIndex(commit => commit.sha === state.last_sha);
    if (previousIndex < 0) {
      await saveTrackerState(config, head.sha);
      logger.warn("GitHub tracker reset its baseline because the previous commit is no longer in recent history", {
        repository: config.githubRepository,
        branch: config.githubBranch,
      });
      return { kind: "history-reset", headSha: head.sha };
    }
    const newCommits = history.slice(0, previousIndex).reverse();
    if (!newCommits.length) {
      await saveTrackerState(config, state.last_sha);
      return { kind: "no-commits" };
    }
    const stats = await fetchCommitStats(newCommits, config);
    const summary = summarizeGitHubActivity(newCommits, stats);
    if (publish && config.githubUpdateChannelId) await publishActivity(client, config, summary);
    const latestCommit = newCommits.at(-1);
    if (!latestCommit) return { kind: "no-commits" };
    await saveTrackerState(config, latestCommit.sha);
    return { kind: "updates", summary, published: publish && Boolean(config.githubUpdateChannelId) };
  } catch (error) {
    const message = error instanceof GitHubTrackerError
      ? error.message
      : "GitHub tracking failed unexpectedly.";
    await saveTrackerState(config, null, message).catch(() => undefined);
    throw error;
  } finally {
    checking = false;
  }
}

export function startGitHubTracker(client: Client, config: BotConfig): void {
  if (timer) return;
  if (!config.githubUpdateChannelId || !config.botModeratorGuildId) {
    logger.info("Automatic GitHub announcements are disabled until GITHUB_UPDATE_CHANNEL_ID and BOT_MODERATOR_GUILD_ID are configured.");
    return;
  }
  const poll = (): void => {
    if (activeCycle) return;
    const task = runGitHubCheck(client, config, true)
      .then(result => {
        if (result.kind === "updates") {
          logger.info("Published a consolidated GitHub activity update", {
            repository: config.githubRepository,
            branch: config.githubBranch,
            commits: result.summary.commits.length,
            statsFor: result.summary.statsFor,
          });
        }
      })
      .catch(error => logger.warn("GitHub tracker polling cycle failed", {
        repository: config.githubRepository,
        branch: config.githubBranch,
        reason: error instanceof Error ? error.message : "Unknown error",
      }))
      .finally(() => {
        if (activeCycle === task) activeCycle = null;
      });
    activeCycle = task;
  };
  poll();
  timer = setInterval(poll, config.githubPollIntervalMinutes * 60_000);
  timer.unref();
  logger.info("GitHub tracker started", { intervalMinutes: config.githubPollIntervalMinutes });
}

export async function stopGitHubTracker(): Promise<void> {
  if (timer) clearInterval(timer);
  timer = null;
  const cycle = activeCycle;
  if (cycle) await cycle;
  activeCycle = null;
}
