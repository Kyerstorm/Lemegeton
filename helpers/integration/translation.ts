import { createHash } from "node:crypto";
import { query, queryOne } from "../../database.js";
import type { TranslationConfig } from "../runtime/config.js";
import { getGuildLanguage } from "../runtime/languages.js";
import { logger } from "../runtime/logger.js";

export type TranslationProvider = "madlad" | "nllb" | "libretranslate";

export interface TranslationResult {
  text: string;
  provider: TranslationProvider;
}

let activeConfig: TranslationConfig | undefined;
const pendingTranslations = new Map<string, Promise<string>>();

export function configureTranslation(config: TranslationConfig): void {
  activeConfig = config;
}

function normalizeTranslation(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const result = value.trim();
  return result.length > 0 && result.length <= 20_000 ? result : null;
}

async function requestModelTranslation(
  endpoint: string,
  apiKey: string | undefined,
  text: string,
  sourceLanguage: string,
  targetLanguage: string,
  timeoutMs: number,
  fetcher: typeof fetch,
): Promise<string> {
  const response = await fetcher(endpoint, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(apiKey ? { authorization: `Bearer ${apiKey}` } : {}),
    },
    body: JSON.stringify({
      text,
      source_language: sourceLanguage,
      target_language: targetLanguage,
    }),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!response.ok) throw new Error(`Translation endpoint returned HTTP ${response.status}.`);
  const body = await response.json() as Record<string, unknown>;
  const result = normalizeTranslation(body.translated_text) ?? normalizeTranslation(body.translatedText);
  if (!result) throw new Error("Translation endpoint returned no valid translated_text.");
  return result;
}

async function requestLibreTranslation(
  endpoint: string,
  apiKey: string | undefined,
  text: string,
  sourceLanguage: string,
  targetLanguage: string,
  timeoutMs: number,
  fetcher: typeof fetch,
): Promise<string> {
  const body = new URLSearchParams({
    q: text,
    source: sourceLanguage,
    target: targetLanguage,
    format: "text",
  });
  if (apiKey) body.set("api_key", apiKey);
  const response = await fetcher(endpoint, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!response.ok) throw new Error(`LibreTranslate returned HTTP ${response.status}.`);
  const payload = await response.json() as Record<string, unknown>;
  const result = normalizeTranslation(payload.translatedText) ?? normalizeTranslation(payload.translated_text);
  if (!result) throw new Error("LibreTranslate returned no valid translation.");
  return result;
}

/**
 * Provider order is MADLAD (primary), NLLB (licensed backup), then LibreTranslate.
 * NLLB is skipped unless the operator explicitly confirms non-commercial use.
 */
export async function translateWithFallback(
  text: string,
  sourceLanguage: string,
  targetLanguage: string,
  config: TranslationConfig,
  fetcher: typeof fetch = fetch,
): Promise<TranslationResult | null> {
  const providers: Array<{ provider: TranslationProvider; run: () => Promise<string> }> = [];

  if (config.madladUrl) {
    providers.push({
      provider: "madlad",
      run: () => requestModelTranslation(
        config.madladUrl!,
        config.madladApiKey,
        text,
        sourceLanguage,
        targetLanguage,
        config.timeoutMs,
        fetcher,
      ),
    });
  }

  if (config.nllbUrl && config.nllbNonCommercialUseConfirmed) {
    providers.push({
      provider: "nllb",
      run: () => requestModelTranslation(
        config.nllbUrl!,
        config.nllbApiKey,
        text,
        sourceLanguage,
        targetLanguage,
        config.timeoutMs,
        fetcher,
      ),
    });
  }

  if (config.libreTranslateUrl) {
    providers.push({
      provider: "libretranslate",
      run: () => requestLibreTranslation(
        config.libreTranslateUrl!,
        config.libreTranslateApiKey,
        text,
        sourceLanguage,
        targetLanguage,
        config.timeoutMs,
        fetcher,
      ),
    });
  }

  for (const provider of providers) {
    try {
      const result = await provider.run();
      if (result !== text) return { text: result, provider: provider.provider };
    } catch {
      // Fall through without exposing source text or provider credentials in logs.
    }
  }

  return null;
}

/**
 * Translate bot-owned, static interface text only. Never pass member content,
 * archive submissions, media titles, provider descriptions, or other user data.
 */
export async function translateUiText(
  text: string,
  targetLanguage: string,
  sourceLanguage = "en",
): Promise<string> {
  const config = activeConfig;
  const target = targetLanguage.trim().toLowerCase();
  if (!config || !text.trim() || text.length > 5000 || target === sourceLanguage) return text;
  if (!/^[a-z]{2,8}$/.test(target) || !/^[a-z]{2,8}$/.test(sourceLanguage)) return text;

  const sourceHash = createHash("sha256").update(text).digest("hex");
  const cacheKey = `${sourceLanguage}:${target}:${sourceHash}`;
  const pending = pendingTranslations.get(cacheKey);
  if (pending) return pending;

  const operation = (async (): Promise<string> => {
    try {
      const cached = await queryOne<{ translated_text: string }>(
        "SELECT translated_text FROM translation_cache WHERE source_language = $1 AND target_language = $2 AND source_hash = $3",
        [sourceLanguage, target, sourceHash],
      );
      if (cached?.translated_text) return cached.translated_text;
    } catch (error) {
      logger.debug("Translation cache lookup unavailable", {
        reason: error instanceof Error ? error.message : "Unknown error",
      });
    }

    const result = await translateWithFallback(text, sourceLanguage, target, config);
    if (!result) return text;

    try {
      await query(
        "INSERT INTO translation_cache (source_language, target_language, source_hash, translated_text, provider) " +
          "VALUES ($1,$2,$3,$4,$5) ON CONFLICT (source_language,target_language,source_hash) " +
          "DO UPDATE SET translated_text = EXCLUDED.translated_text, provider = EXCLUDED.provider, created_at = NOW()",
        [sourceLanguage, target, sourceHash, result.text, result.provider],
      );
    } catch (error) {
      logger.debug("Translation cache write unavailable", {
        provider: result.provider,
        reason: error instanceof Error ? error.message : "Unknown error",
      });
    }
    return result.text;
  })();

  pendingTranslations.set(cacheKey, operation);
  try {
    return await operation;
  } finally {
    if (pendingTranslations.get(cacheKey) === operation) pendingTranslations.delete(cacheKey);
  }
}

export async function translateGuildUiText(guildId: string, text: string): Promise<string> {
  try {
    const language = await getGuildLanguage(guildId);
    return language ? translateUiText(text, language.code) : text;
  } catch (error) {
    logger.debug("Guild language could not be resolved for translation", {
      guildId,
      reason: error instanceof Error ? error.message : "Unknown error",
    });
    return text;
  }
}
