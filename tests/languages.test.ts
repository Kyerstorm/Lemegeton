import test from "node:test";
import assert from "node:assert/strict";
import { PermissionFlagsBits } from "discord.js";
import { LanguageCommand } from "../src/commands/language.js";
import {
  SUPPORTED_LANGUAGES,
  getSupportedLanguage,
  searchSupportedLanguages,
} from "../helpers/runtime/languages.js";

test("the server language picker contains more than 100 ISO language options", () => {
  assert.ok(SUPPORTED_LANGUAGES.length >= 100);
  assert.equal(new Set(SUPPORTED_LANGUAGES.map(language => language.code)).size, SUPPORTED_LANGUAGES.length);
});

test("supported languages resolve case-insensitively by ISO language code", () => {
  assert.equal(getSupportedLanguage("EN")?.code, "en");
  assert.equal(getSupportedLanguage("ja")?.code, "ja");
  assert.equal(getSupportedLanguage("xx"), null);
});

test("language autocomplete searches names, native names and codes with Discord's 25-result cap", () => {
  assert.ok(searchSupportedLanguages("Spanish").some(language => language.code === "es"));
  assert.ok(searchSupportedLanguages("español").some(language => language.code === "es"));
  assert.ok(searchSupportedLanguages("zh").some(language => language.code === "zh"));
  assert.equal(searchSupportedLanguages("", 100).length, 25);
});

test("the /language command exposes exactly one required autocomplete option", () => {
  const command = new LanguageCommand();
  const definition = command.data.toJSON();
  assert.equal(definition.options?.length, 1);
  assert.equal(definition.options?.[0]?.name, "language");
  const option = definition.options?.[0];
  assert.ok(option);
  assert.equal("autocomplete" in option && option.autocomplete, true);
  assert.equal(option.required, true);
  assert.equal(definition.default_member_permissions, String(PermissionFlagsBits.ManageGuild));
});
