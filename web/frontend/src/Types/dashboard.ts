export type User = {
  id: string;
  username: string;
  global_name?: string | null;
  avatar?: string | null;
};

export type Guild = {
  id: string;
  name: string;
  icon?: string | null;
  administrator?: boolean;
  can_manage_server?: boolean;
  member_count?: number | null;
  bot_installed: boolean;
  invite_url?: string | null;
};


export type ArchiveSettings = {
  enabledCategories: string[];
  uploadTypes: string[];
  uploadChannelId: string | null;
  legacyStorageChannelId: string | null;
  moderationChannelId: string | null;
  moderatorRoleId: string | null;
};

export type ArchiveSettingsResponse = {
  settings: ArchiveSettings;
  categories: { label: string; value: string }[];
  upload_types: { label: string; value: string }[];
  channels: { id: string; name: string; type: number }[];
  roles: { id: string; name: string }[];
};

export type DashboardServerSettings = {
  settings: {
    leave_action: "delete" | "retain" | null;
    language_code: string;
  };
  setup_complete: boolean;
  can_choose_retention: boolean;
  can_manage_server: boolean;
  languages: { code: string; label: string }[];
};

export type Command = {
  fullname: string;
  name?: string;
  description?: string;
  section?: string;
  type?: string;
  scope?: string;
  enabled: boolean;
  configurable?: boolean;
  protected?: boolean;
  required_permissions?: string | boolean | null;
};

export type AuditEntry = {
  id?: string;
  action?: string;
  details?: string;
  actor_name?: string;
  actor_id?: string;
  ts?: string;
};

export type Overview = {
  bot?: {
    ready?: boolean;
    status?: string;
    latency_ms?: number | null;
    member_count?: number | null;
    guild_count?: number | null;
    command_count?: number | null;
  };
};

export type SystemStatus = {
  status?: string;
  ready?: boolean;
  reason?: string;
  observed_at?: number;
  last_known?: Record<string, unknown> | null;
  uptime_seconds?: number | null;
  node_version?: string;
  commands?: string[];
  command_count?: number | null;
  latency_ms?: number | null;
  guild_count?: number | null;
};

export type Resource = {
  name?: string;
  purpose?: string;
  detail?: string;
  state?: string;
};

export type Integration = {
  name?: string;
  detail?: string;
  configured?: boolean;
};

export type Toast = {
  id: number;
  message: string;
  error: boolean;
  pending?: boolean;
};

export type Confirmation = {
  title: string;
  message: string;
  actionLabel: string;
  destructive?: boolean;
  run: () => Promise<void>;
};

export type Bootstrap = {
  user: User;
  guilds: Guild[];
  csrf_token: string;
  selected_guild_id?: string;
  bot_moderator?: boolean;
};

export type CookiePreferences = {
  saved: boolean;
  remember_server: boolean;
  consent_version: string;
  decided_at?: number | null;
  expires_at?: number | null;
};

export type DashboardConsent = {
  accepted: boolean;
  versions: {
    terms: string;
    privacy: string;
    guidelines: string;
  };
  policies: { label: string; url: string }[];
};

export type CommandResponse = {
  commands: Command[];
  revision: string;
};

export type CommandAccessPolicy = {
  role_mode: "everyone" | "include" | "exclude";
  role_ids: string[];
  channel_mode: "all" | "include" | "exclude";
  channel_ids: string[];
  revision: number;
};

export type CommandAccessResponse = {
  roles: { id: string; name: string }[];
  channels: { id: string; name: string; type: number }[];
  policies: Record<string, CommandAccessPolicy>;
};

export type DashboardSection =
  | "overview"
  | "commands"
  | "system"
  | "audit"
  | "logs"
  | "integrations"
  | "database";

export type SectionLoadState = {
  loading: boolean;
  loaded: boolean;
  error: string;
  errorStatus: number | null;
};

export type ListResponse<T> = {
  entries?: T[];
  next_cursor?: string | null;
  has_more?: boolean;
};

export type AtlasRelation = {
  title: string;
  category: string;
  url: string | null;
  relationType: string;
  source: string;
  sourceKind: "provider" | "recommendation" | "community";
  provider?: string | null;
  providerId?: string | null;
  evidence?: string | null;
};

export type AtlasGraphNode = {
  id: string;
  title: string;
  category: string;
  url: string | null;
  depth: number;
  provider?: string | null;
  providerId?: string | null;
  imageUrl?: string | null;
  sourceKind?: AtlasRelation["sourceKind"];
  sourceLabel?: string;
  relationType?: string;
};

export type AtlasGraphEdge = {
  from: string;
  to: string;
  relationType: string;
  sourceLabel: string;
  sourceKind: AtlasRelation["sourceKind"];
  evidence?: string | null;
};

export type AtlasResponse = {
  root: {
    title: string;
    category: string;
    url: string | null;
    provider?: string | null;
    providerId?: string | null;
  };
  relationships: AtlasRelation[];
  graph?: {
    rootId: string;
    nodes: AtlasGraphNode[];
    edges: AtlasGraphEdge[];
    truncated: boolean;
  };
  clusters?: { category: string; nodeIds: string[]; count: number }[];
  path?: { nodes: AtlasGraphNode[]; edges: AtlasGraphEdge[] } | null;
  export?: { filename: string; mimeType: string; base64: string };
};
