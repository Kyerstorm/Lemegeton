const LOW_SIGNAL_TOKENS = new Set(["a", "an", "and", "for", "in", "of", "on", "or", "the", "to", "with"]);

export function normalizeTitleSearchValue(value: string): string {
  return value.normalize("NFKD").replace(/\p{M}/gu, "").toLocaleLowerCase("en")
    .replace(/[^\p{L}\p{N}]+/gu, " ").trim();
}

function searchTokens(value: string): string[] {
  const tokens = value.split(" ").filter(Boolean);
  const meaningful = tokens.filter(token => !LOW_SIGNAL_TOKENS.has(token));
  return meaningful.length ? meaningful : tokens;
}

function tokenMatches(queryToken: string, titleToken: string): boolean {
  return queryToken === titleToken || (queryToken.length >= 3 && titleToken.startsWith(queryToken));
}

export function scoreTitleSearchMatch(query: string, titles: readonly string[]): number {
  const normalizedQuery = normalizeTitleSearchValue(query);
  if (!normalizedQuery) return 0;
  const queryTokens = searchTokens(normalizedQuery);
  let best = 0;
  for (const title of titles) {
    const normalizedTitle = normalizeTitleSearchValue(title);
    if (!normalizedTitle) continue;
    if (normalizedTitle === normalizedQuery) return 1_000;
    if (normalizedTitle.endsWith(normalizedQuery)) {
      best = Math.max(best, 850 - Math.min(100, normalizedTitle.length - normalizedQuery.length));
      continue;
    }
    if (normalizedTitle.startsWith(normalizedQuery)) {
      best = Math.max(best, 850 - Math.min(100, normalizedTitle.length - normalizedQuery.length));
      continue;
    }
    if (normalizedTitle.includes(normalizedQuery)) {
      best = Math.max(best, 700 - Math.min(100, normalizedTitle.length - normalizedQuery.length));
      continue;
    }

    const titleTokens = searchTokens(normalizedTitle);
    const matched = queryTokens.filter(queryToken => titleTokens.some(titleToken => tokenMatches(queryToken, titleToken))).length;
    if (!matched) continue;

    const coverage = matched / queryTokens.length;
    const precision = matched / Math.max(queryTokens.length, titleTokens.length);
    let cursor = -1;
    let orderedMatches = 0;
    let adjacentMatches = 0;
    for (const queryToken of queryTokens) {
      const next = titleTokens.findIndex((titleToken, index) => index > cursor && tokenMatches(queryToken, titleToken));
      if (next < 0) continue;
      if (cursor >= 0 && next === cursor + 1) adjacentMatches += 1;
      orderedMatches += 1;
      cursor = next;
    }
    const orderBonus = Math.round(
      80 * orderedMatches / queryTokens.length
      + 40 * adjacentMatches / Math.max(1, queryTokens.length - 1),
    );
    best = Math.max(best, Math.round(500 * coverage + 100 * precision + orderBonus));
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
