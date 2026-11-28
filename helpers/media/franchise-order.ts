export interface ReleaseDate {
  year: number | null;
  month: number | null;
  day: number | null;
}

export interface ReleaseOrderEntry {
  title: string;
  url: string | null;
  date: string;
  sortKey: number;
}

function completeDate(date: ReleaseDate | null | undefined): ReleaseOrderEntry["date"] | null {
  if (!date || !Number.isInteger(date.year) || !Number.isInteger(date.month) || !Number.isInteger(date.day)) return null;
  const year = date.year as number;
  const month = date.month as number;
  const day = date.day as number;
  const parsed = new Date(Date.UTC(year, month - 1, day));
  if (year < 1 || month < 1 || month > 12
    || parsed.getUTCFullYear() !== year || parsed.getUTCMonth() !== month - 1 || parsed.getUTCDate() !== day) return null;
  return String(year).padStart(4, "0") + "-" + String(month).padStart(2, "0") + "-" + String(day).padStart(2, "0");
}

function sortKey(date: string): number {
  return Number(date.replaceAll("-", ""));
}

function sortEntries(entries: ReleaseOrderEntry[]): ReleaseOrderEntry[] {
  return entries.sort((left, right) => left.sortKey - right.sortKey || left.title.localeCompare(right.title));
}

export function aniListReleaseOrder(
  seed: { title: string; url: string | null; startDate: ReleaseDate | null },
  relations: readonly { title: string; url: string; startDate: ReleaseDate | null }[],
): ReleaseOrderEntry[] | null {
  if (!relations.length) return null;
  const items = [seed, ...relations].map(item => {
    const date = completeDate(item.startDate);
    return date ? { title: item.title, url: item.url, date, sortKey: sortKey(date) } : null;
  });
  if (items.some(item => item === null)) return null;
  return sortEntries(items as ReleaseOrderEntry[]).slice(0, 15);
}

export function tmdbCollectionReleaseOrder(
  items: readonly { title: string; sourceUrl: string; releaseDate: string | null }[],
): ReleaseOrderEntry[] | null {
  if (items.length < 2) return null;
  const entries = items.map(item => {
    const raw = item.releaseDate;
    if (!raw || !/^\d{4}-\d{2}-\d{2}$/.test(raw)) return null;
    const [year, month, day] = raw.split("-").map(Number);
    const date = completeDate({ year: year ?? null, month: month ?? null, day: day ?? null });
    return date ? { title: item.title, url: item.sourceUrl, date, sortKey: sortKey(date) } : null;
  });
  if (entries.some(item => item === null)) return null;
  return sortEntries(entries as ReleaseOrderEntry[]).slice(0, 15);
}
