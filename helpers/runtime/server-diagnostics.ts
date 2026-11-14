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
    { name: "S3-compatible asset storage", configured: snapshot.objectStorageConfigured, detail: snapshot.objectStorageConfigured ? "Endpoint, bucket and credentials are configured." : "Complete endpoint, bucket and credential configuration is not present." },
  ];
}
