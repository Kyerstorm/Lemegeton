export function normalizeTitleSearchValue(value: string): string {
  return value.normalize("NFKD").replace(/\p{M}/gu, "").toLocaleLowerCase("en")
    .replace(/[^\p{L}\p{N}]+/gu, " ").trim();
}

export function scoreTitleSearchMatch(query: string, titles: readonly string[]): number {
  const normalizedQuery = normalizeTitleSearchValue(query);
  if (!normalizedQuery) return 0;
  const queryTokens = normalizedQuery.split(" ").filter(Boolean);
  let best = 0;
  for (const title of titles) {
    const normalizedTitle = normalizeTitleSearchValue(title);
    if (!normalizedTitle) continue;
    if (normalizedTitle === normalizedQuery) return 1_000;
    if (normalizedTitle.startsWith(normalizedQuery)) {
      best = Math.max(best, 850 - Math.min(100, normalizedTitle.length - normalizedQuery.length));
      continue;
    }
    if (normalizedTitle.includes(normalizedQuery)) {
      best = Math.max(best, 700 - Math.min(100, normalizedTitle.length - normalizedQuery.length));
      continue;
    }
    const titleTokens = new Set(normalizedTitle.split(" ").filter(Boolean));
    const matched = queryTokens.filter(token => titleTokens.has(token)).length;
    if (matched) {
      const coverage = matched / queryTokens.length;
      const precision = matched / Math.max(queryTokens.length, titleTokens.size);
      best = Math.max(best, Math.round(450 * coverage + 150 * precision));
    }
  }
  return best;
}

export function rankTitleSearchResults<T>(
  query: string,
  records: readonly T[],
  getTitles: (record: T) => readonly string[],
): T[] {
  if (!normalizeTitleSearchValue(query) || records.length < 2) return [...records];
  return records.map((record, index) => ({
    record,
    index,
    score: scoreTitleSearchMatch(query, getTitles(record)),
  })).sort((left, right) => right.score - left.score || left.index - right.index)
    .map(item => item.record);
}
