import test from "node:test";
import assert from "node:assert/strict";
import { translateWithFallback } from "../helpers/integration/translation.js";
import type { TranslationConfig } from "../helpers/runtime/config.js";

function config(overrides: Partial<TranslationConfig> = {}): TranslationConfig {
  return {
    madladUrl: null,
    nllbUrl: null,
    nllbNonCommercialUseConfirmed: false,
    libreTranslateUrl: null,
    timeoutMs: 1000,
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

test("uses MADLAD as the primary translation provider", async () => {
  const calls: string[] = [];
  const result = await translateWithFallback(
    "Hello",
    "en",
    "de",
    config({ madladUrl: "https://madlad.test/translate", nllbUrl: "https://nllb.test/translate", nllbNonCommercialUseConfirmed: true }),
    async (input) => {
      calls.push(String(input));
      return jsonResponse({ translated_text: "Hallo" });
    },
  );
  assert.deepEqual(result, { text: "Hallo", provider: "madlad" });
  assert.deepEqual(calls, ["https://madlad.test/translate"]);
});

test("skips the NLLB backup until non-commercial use is explicitly confirmed", async () => {
  let requests = 0;
  const result = await translateWithFallback(
    "Hello",
    "en",
    "de",
    config({ nllbUrl: "https://nllb.test/translate" }),
    async () => {
      requests += 1;
      return jsonResponse({ translated_text: "Hallo" });
    },
  );
  assert.equal(result, null);
  assert.equal(requests, 0);
});

test("falls back from MADLAD to NLLB when NLLB is permitted", async () => {
  const calls: string[] = [];
  const result = await translateWithFallback(
    "Hello",
    "en",
    "de",
    config({ madladUrl: "https://madlad.test/translate", nllbUrl: "https://nllb.test/translate", nllbNonCommercialUseConfirmed: true }),
    async (input) => {
      calls.push(String(input));
      if (String(input).includes("madlad")) return jsonResponse({ error: "offline" }, 503);
      return jsonResponse({ translated_text: "Hallo" });
    },
  );
  assert.deepEqual(result, { text: "Hallo", provider: "nllb" });
  assert.deepEqual(calls, ["https://madlad.test/translate", "https://nllb.test/translate"]);
});

test("uses LibreTranslate only after the model endpoints fail", async () => {
  const calls: string[] = [];
  const result = await translateWithFallback(
    "Hello",
    "en",
    "de",
    config({
      madladUrl: "https://madlad.test/translate",
      nllbUrl: "https://nllb.test/translate",
      nllbNonCommercialUseConfirmed: true,
      libreTranslateUrl: "https://libre.test/translate",
    }),
    async (input, init) => {
      calls.push(String(input));
      if (String(input).includes("libre")) {
        const body = String(init?.body);
        assert.match(body, /q=Hello/);
        assert.match(body, /source=en/);
        assert.match(body, /target=de/);
        return jsonResponse({ translatedText: "Hallo" });
      }
      return jsonResponse({}, 503);
    },
  );
  assert.deepEqual(result, { text: "Hallo", provider: "libretranslate" });
  assert.deepEqual(calls, [
    "https://madlad.test/translate",
    "https://nllb.test/translate",
    "https://libre.test/translate",
  ]);
});

test("returns null when no configured provider returns a valid translation", async () => {
  const result = await translateWithFallback(
    "Hello",
    "en",
    "de",
    config(),
    async () => jsonResponse({ translated_text: "" }),
  );
  assert.equal(result, null);
});
