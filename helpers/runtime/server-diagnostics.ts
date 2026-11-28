export interface ChannelPermissionSnapshot {
  viewChannel: boolean;
  sendMessages: boolean;
  embedLinks: boolean;
}

export function missingChannelPermissions(snapshot: ChannelPermissionSnapshot): string[] {
  const missing: string[] = [];
  if (!snapshot.viewChannel) missing.push("View Channel");
  if (!snapshot.sendMessages) missing.push("Send Messages");
  if (!snapshot.embedLinks) missing.push("Embed Links");
  return missing;
}


export interface JobQueueSnapshot { name: string; due_count: number; failed_count: number; stale_count: number; }
export interface JobQueueCheck { name: string; status: "Healthy" | "Backlog" | "Needs attention"; detail: string; }
export function jobQueueChecks(snapshots: readonly JobQueueSnapshot[]): JobQueueCheck[] {
  return snapshots.map(snapshot => {
    const due = Math.max(0, Number(snapshot.due_count) || 0);
    const failed = Math.max(0, Number(snapshot.failed_count) || 0);
    const stale = Math.max(0, Number(snapshot.stale_count) || 0);
    const status = failed > 0 || stale > 0 ? "Needs attention" : due > 0 ? "Backlog" : "Healthy";
    return { name: snapshot.name, status, detail: [due + " due", failed + " failed", stale + " expired claims"].join(" · ") + "." };
  });
}
export interface ProviderConfigurationSnapshot {
  aniListEndpointConfigured: boolean;
  tmdbCredentialsConfigured: boolean;
  googleBooksKeyConfigured: boolean;
  igdbCredentialsConfigured: boolean;
  steamKeyConfigured: boolean;
  objectStorageConfigured: boolean;
}

export interface ProviderConfigurationCheck {
  name: string;
  configured: boolean;
  detail: string;
}

export function providerConfigurationChecks(snapshot: ProviderConfigurationSnapshot): ProviderConfigurationCheck[] {
  return [
    { name: "AniList", configured: snapshot.aniListEndpointConfigured, detail: snapshot.aniListEndpointConfigured ? "GraphQL endpoint is configured." : "GraphQL endpoint is missing." },
    { name: "TMDB", configured: snapshot.tmdbCredentialsConfigured, detail: snapshot.tmdbCredentialsConfigured ? "Bearer credentials are configured." : "Bearer credentials are not configured." },
    { name: "Google Books", configured: snapshot.googleBooksKeyConfigured, detail: snapshot.googleBooksKeyConfigured ? "API key is configured." : "API key is not configured." },
    { name: "IGDB", configured: snapshot.igdbCredentialsConfigured, detail: snapshot.igdbCredentialsConfigured ? "Client credentials are configured." : "Client credentials are incomplete or missing." },
    { name: "Steam", configured: snapshot.steamKeyConfigured, detail: snapshot.steamKeyConfigured ? "API key is configured." : "API key is not configured." },
    { name: "RocksDB private asset storage", configured: snapshot.objectStorageConfigured, detail: snapshot.objectStorageConfigured ? "The local private object-store path is configured." : "The private object-store path is missing." },
  ];
}
