import { query, queryOne } from "../../database.js";

const LANGUAGE_CODES = "aa ab ae af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs ca ce ch co cr cs cu cv cy da de dv dz ee el en eo es et eu fa ff fi fj fo fr fy ga gd gl gn gu gv ha he hi ho hr ht hu hy hz ia id ie ig ii ik io is it iu ja jv ka kg ki kj kk kl km kn ko kr ks ku kv kw ky la lb lg li ln lo lt lu lv mg mh mi mk ml mn mr ms mt my na nb nd ne ng nl nn no nr nv ny oc oj om or os pa pi pl ps pt qu rm rn ro rw sa sc sd se sg si sk sl sm sn so sq sr ss st su sv sw ta te tg th ti tk tl tn to tr ts tt tw ty ug uk ur uz ve vi vo wa wo xh yi yo za zh zu".split(" ").filter(Boolean);

const englishNames = new Intl.DisplayNames(["en"], { type: "language" });

export interface SupportedLanguage {
  code: string;
  name: string;
  nativeName: string;
  label: string;
}

export const SUPPORTED_LANGUAGES: readonly SupportedLanguage[] = Object.freeze(
  LANGUAGE_CODES.map((code) => {
    const name = englishNames.of(code) ?? code.toUpperCase();
    const nativeName = new Intl.DisplayNames([code], { type: "language" }).of(code) ?? name;
    return {
      code,
      name,
      nativeName,
      label: name === nativeName ? name : name + " · " + nativeName,
    };
  }).sort((a, b) => a.name.localeCompare(b.name, "en")),
);

const languageByCode = new Map(SUPPORTED_LANGUAGES.map((language) => [language.code, language]));

export function getSupportedLanguage(code: unknown): SupportedLanguage | null {
  if (typeof code !== "string") return null;
  return languageByCode.get(code.trim().toLowerCase()) ?? null;
}

export function searchSupportedLanguages(input: string, limit = 25): SupportedLanguage[] {
  const term = input.trim().toLocaleLowerCase();
  const matches = term
    ? SUPPORTED_LANGUAGES.filter((language) =>
        language.code.includes(term) ||
        language.name.toLocaleLowerCase().includes(term) ||
        language.nativeName.toLocaleLowerCase().includes(term),
      )
    : [...SUPPORTED_LANGUAGES];
  return matches.slice(0, Math.max(0, Math.min(25, limit)));
}

export async function getGuildLanguage(guildId: string): Promise<SupportedLanguage | null> {
  const row = await queryOne<{ language_code: string }>(
    "SELECT language_code FROM guild_language_settings WHERE guild_id = $1",
    [guildId],
  );
  return getSupportedLanguage(row?.language_code);
}

export async function isGuildLanguageConfigured(guildId: string): Promise<boolean> {
  return (await getGuildLanguage(guildId)) !== null;
}

export async function setGuildLanguage(guildId: string, code: string, actorId: string): Promise<SupportedLanguage> {
  const language = getSupportedLanguage(code);
  if (!language) throw new Error("Choose a language from the supported language list.");
  await query(
    "INSERT INTO guild_language_settings (guild_id, language_code, updated_by) " +
    "VALUES ($1,$2,$3) " +
    "ON CONFLICT (guild_id) DO UPDATE SET language_code = EXCLUDED.language_code, " +
    "updated_by = EXCLUDED.updated_by, updated_at = NOW()",
    [guildId, language.code, actorId],
  );
  return language;
}
