export function formatMetadataSourceReference(
  provider: string,
  recordId: string | number,
  sourceUrl: string,
): string {
  const providerLabel = provider.replace(/[\r\n\[\]()<>`]/g, "").trim().slice(0, 40) || "Metadata provider";
  const identifier = String(recordId).replace(/[\r\n`]/g, "").trim().slice(0, 100) || "Unavailable";
  let source = "Source link unavailable";
  try {
    const url = new URL(sourceUrl);
    if (url.protocol === "https:" && !url.username && !url.password) {
      source = `[Open ${providerLabel} record](${url.toString()})`;
    }
  } catch {
    // Keep the source identifier visible when a provider link is malformed.
  }
  return `Record ID: ${identifier}\n${source}`;
}
