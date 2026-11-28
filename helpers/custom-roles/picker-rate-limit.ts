export const MAX_RATE_LIMIT_KEYS = 10_000;
const CAPACITY_SWEEP_INTERVAL_MS = 5_000;
const lastCapacitySweep = new WeakMap<Map<string, number[]>, number>();

export function rateLimitCount(
  buckets: Map<string, number[]>,
  key: string,
  windowMs: number,
  now: number,
): number {
  const cutoff = now - windowMs;
  const current = buckets.get(key);
  if (current) {
    while (current.length && current[0]! <= cutoff) current.shift();
    if (!current.length) buckets.delete(key);
  }

  const lastSweep = lastCapacitySweep.get(buckets) ?? Number.NEGATIVE_INFINITY;
  if (buckets.size >= MAX_RATE_LIMIT_KEYS && now - lastSweep >= CAPACITY_SWEEP_INTERVAL_MS) {
    lastCapacitySweep.set(buckets, now);
    for (const [candidate, entries] of buckets) {
      while (entries.length && entries[0]! <= cutoff) entries.shift();
      if (!entries.length) buckets.delete(candidate);
    }
  }

  return buckets.get(key)?.length ?? 0;
}

export function recordRateLimit(
  buckets: Map<string, number[]>,
  key: string,
  windowMs: number,
  now: number,
): boolean {
  rateLimitCount(buckets, key, windowMs, now);
  let entries = buckets.get(key);
  if (!entries) {
    if (buckets.size >= MAX_RATE_LIMIT_KEYS) return false;
    entries = [];
    buckets.set(key, entries);
  }
  entries.push(now);
  return true;
}
