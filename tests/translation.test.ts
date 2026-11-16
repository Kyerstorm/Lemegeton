import test from "node:test";
import assert from "node:assert/strict";
import { translateWithFallback } from "../helpers/integration/translation.js";
import type { TranslationConfig } from "../helpers/runtime/config.js";

function config(overrides: Partial<TranslationConfig> = {}): TranslationConfig {
  return {
    madladUrl: null,
    deeplUrl: null,
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
    config({
      madladUrl: "https://madlad.test/translate",
      deeplUrl: "https://api-free.deepl.test/v2/translate",
      deeplApiKey: "deepl-token",
      nllbUrl: "https://nllb.test/translate",
      nllbNonCommercialUseConfirmed: true,
    }),
    async (input) => {
      calls.push(String(input));
      return jsonResponse({ translated_text: "Hallo" });
    },
  );
  assert.deepEqual(result, { text: "Hallo", provider: "madlad" });
  assert.deepEqual(calls, ["https://madlad.test/translate"]);
});

test("uses DeepL after MADLAD and before NLLB", async () => {
  const calls: string[] = [];
  let deeplHeaders: HeadersInit | undefined;
  let deeplBody: Record<string, unknown> | undefined;
  const result = await translateWithFallback(
    "Hello",
    "en",
    "de",
    config({
      madladUrl: "https://madlad.test/translate",
      deeplUrl: "https://api-free.deepl.test/v2/translate",
      deeplApiKey: "deepl-token",
      nllbUrl: "https://nllb.test/translate",
      nllbNonCommercialUseConfirmed: true,
    }),
    async (input, init) => {
      const url = String(input);
      calls.push(url);
      if (url.includes("madlad")) return jsonResponse({}, 503);
      if (url.includes("deepl")) {
        deeplHeaders = init?.headers;
        deeplBody = JSON.parse(String(init?.body)) as Record<string, unknown>;
        return jsonResponse({ translations: [{ text: "Hallo" }] });
      }
      return jsonResponse({ translated_text: "NLLB" });
    },
  );
  assert.deepEqual(result, { text: "Hallo", provider: "deepl" });
  assert.deepEqual(calls, ["https://madlad.test/translate", "https://api-free.deepl.test/v2/translate"]);
  assert.equal(new Headers(deeplHeaders).get("authorization"), "DeepL-Auth-Key deepl-token");
  assert.deepEqual(deeplBody, { text: ["Hello"], source_lang: "EN", target_lang: "DE" });
});

test("skips the NLLB backup until non-commercial use is explicitly confirmed", async () => {
  let requests = 0;
  const result = await translateWithFallback("Hello","en","de",config({nllbUrl:"https://nllb.test/translate"}),async () => {
    requests += 1;
    return jsonResponse({ translated_text: "Hallo" });
  });
  assert.equal(result, null);
  assert.equal(requests, 0);
});

test("falls back from MADLAD to NLLB when NLLB is permitted and DeepL is not configured", async () => {
  const calls: string[] = [];
  const result = await translateWithFallback(
    "Hello",
    "en",
    "de",
    config({ madladUrl:"https://madlad.test/translate", nllbUrl:"https://nllb.test/translate", nllbNonCommercialUseConfirmed:true }),
    async (input) => {
      calls.push(String(input));
      if (String(input).includes("madlad")) return jsonResponse({ error:"offline" },503);
      return jsonResponse({ translated_text:"Hallo" });
    },
  );
  assert.deepEqual(result,{text:"Hallo",provider:"nllb"});
  assert.deepEqual(calls,["https://madlad.test/translate","https://nllb.test/translate"]);
});

test("uses LibreTranslate only after the model endpoints fail", async () => {
  const calls: string[] = [];
  const result = await translateWithFallback(
    "Hello",
    "en",
    "de",
    config({
      madladUrl:"https://madlad.test/translate",
      nllbUrl:"https://nllb.test/translate",
      nllbNonCommercialUseConfirmed:true,
      libreTranslateUrl:"https://libre.test/translate",
    }),
    async (input,init) => {
      const url=String(input);
      calls.push(url);
      if(url.includes("libre")){
        const body=String(init?.body);
        assert.match(body,/q=Hello/);
        assert.match(body,/source=en/);
        assert.match(body,/target=de/);
        return jsonResponse({translatedText:"Hallo"});
      }
      return jsonResponse({},503);
    },
  );
  assert.deepEqual(result,{text:"Hallo",provider:"libretranslate"});
  assert.deepEqual(calls,["https://madlad.test/translate","https://nllb.test/translate","https://libre.test/translate"]);
});

test("uses Google Cloud Translation as the final fallback after LibreTranslate", async () => {
  const calls: string[] = [];
  let googleBody: Record<string, unknown> | undefined;
  const result = await translateWithFallback(
    "Hello",
    "en",
    "de",
    config({
      madladUrl:"https://madlad.test/translate",
      deeplUrl:"https://api-free.deepl.test/v2/translate",
      deeplApiKey:"deepl-token",
      nllbUrl:"https://nllb.test/translate",
      nllbNonCommercialUseConfirmed:true,
      libreTranslateUrl:"https://libre.test/translate",
      googleTranslateApiKey:"google-secret",
    }),
    async (input,init) => {
      const url=new URL(String(input));
      calls.push(url.origin+url.pathname);
      if(url.hostname==="translation.googleapis.com"){
        assert.equal(url.searchParams.get("key"),"google-secret");
        googleBody=JSON.parse(String(init?.body)) as Record<string,unknown>;
        return jsonResponse({data:{translations:[{translatedText:"Hallo &amp; willkommen &#39;!"}]}});
      }
      return jsonResponse({},503);
    },
  );
  assert.deepEqual(result,{text:"Hallo & willkommen '!",provider:"googletranslate"});
  assert.deepEqual(calls,[
    "https://madlad.test/translate",
    "https://api-free.deepl.test/v2/translate",
    "https://nllb.test/translate",
    "https://libre.test/translate",
    "https://translation.googleapis.com/language/translate/v2",
  ]);
  assert.deepEqual(googleBody,{q:"Hello",source:"en",target:"de",format:"text"});
});

test("returns null when no configured provider returns a valid translation", async () => {
  const result = await translateWithFallback("Hello","en","de",config(),async () => jsonResponse({translated_text:""}));
  assert.equal(result,null);
});
