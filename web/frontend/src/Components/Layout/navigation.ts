import type { IconName } from "../Icons";

export type Page = "overview" | "commands" | "archive" | "settings" | "atlas" | "registry" | "audit" | "diagnostics" | "logs" | "integrations" | "database";
export type PageMetadata = { id: Page; label: string; icon: IconName; eyebrow: string; subtitle: string };

export const PAGES: { id: Page; label: string; icon: IconName; eyebrow: string; subtitle: string }[] = [
  { id: "overview", label: "Overview", icon: "overview", eyebrow: "LIVE CONTROL / 01", subtitle: "A clear view of bot health and the current server configuration." },
  { id: "commands", label: "Commands", icon: "commands", eyebrow: "COMMAND REGISTRY / 02", subtitle: "Control the registered command set and per-server access rules." },
  { id: "archive", label: "Archive", icon: "archive", eyebrow: "ARCHIVE CONFIGURATION / 03", subtitle: "Set visible collections, accepted uploads and server channels." },
  { id: "settings", label: "Server settings", icon: "settings", eyebrow: "SERVER SETUP / 04", subtitle: "Manage server language and data-retention preferences." },
  { id: "atlas", label: "Knowledge Atlas", icon: "atlas", eyebrow: "MEDIA GRAPH / 05", subtitle: "Explore source-attributed media relationships and the connections approved by this server." },
  { id: "registry", label: "Global registry", icon: "commands", eyebrow: "GLOBAL COMMANDS / 06", subtitle: "Inspect slash commands registered by the live bot process. Per-server availability is managed separately." },
  { id: "audit", label: "Audit history", icon: "audit", eyebrow: "CHANGE RECORD / 07", subtitle: "Review recorded dashboard configuration changes for this server." },
  { id: "diagnostics", label: "Diagnostics", icon: "diagnostics", eyebrow: "HEALTH & TELEMETRY / 08", subtitle: "Inspect the bot gateway, runtime version, uptime, and last-known status." },
  { id: "logs", label: "Runtime logs", icon: "logs", eyebrow: "RUNTIME OUTPUT / 09", subtitle: "Inspect recent operational logs. Bot moderators only." },
  { id: "integrations", label: "Integrations", icon: "integrations", eyebrow: "CONNECTED SERVICES / 10", subtitle: "Inspect bot-wide provider configuration. Bot moderators only." },
  { id: "database", label: "Persistence", icon: "database", eyebrow: "PERSISTENCE / 11", subtitle: "Inspect the saved resources supporting per-guild command settings." }
];
