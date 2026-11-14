export interface ProviderHttpRetryOptions {
  maxAttempts?: number;
  maxRetryDelayMs?: number;
  retryPost?: boolean;
  sleep?: (milliseconds: number) => Promise<void>;
}

const RETRYABLE_STATUS = new Set([408, 425, 429, 500, 502, 503, 504]);

function retryAfterMilliseconds(response: Response): number | null {
  const value = response.headers.get("retry-after");
  if (!value) return null;
  const seconds = Number(value);
  if (Number.isFinite(seconds) && seconds >= 0) return seconds * 1_000;
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? Math.max(0, timestamp - Date.now()) : null;
}

const delay = (milliseconds: number) => new Promise<void>(resolve => setTimeout(resolve, milliseconds));

/** Retries bounded transient HTTP responses for provider read requests. Network errors and timeouts are surfaced to the caller. */
export async function fetchProviderResponse(
  fetcher: typeof fetch,
  input: RequestInfo | URL,
  init: RequestInit = {},
  options: ProviderHttpRetryOptions = {},
): Promise<Response> {
  const method = (init.method ?? "GET").toUpperCase();
  const retryableMethod = method === "GET" || method === "HEAD" || (method === "POST" && options.retryPost === true);
  const maxAttempts = Math.max(1, Math.min(3, Math.floor(options.maxAttempts ?? 3)));
  const maxRetryDelayMs = Math.max(0, Math.min(10_000, Math.floor(options.maxRetryDelayMs ?? 5_000)));
  const sleep = options.sleep ?? delay;

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    const response = await fetcher(input, init);
    if (!retryableMethod || !RETRYABLE_STATUS.has(response.status) || attempt === maxAttempts) return response;

    const serverDelay = retryAfterMilliseconds(response);
    if (serverDelay !== null && serverDelay > maxRetryDelayMs) return response;
    const backoff = Math.min(200 * 2 ** (attempt - 1), maxRetryDelayMs);
    await sleep(serverDelay ?? backoff);
  }

  throw new Error("Provider request exhausted its retry attempts without a response.");
}
