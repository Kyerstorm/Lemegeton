import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { closeDatabase, initDatabase, query, queryOne, transaction, backfillAtlasProviderIdentities } from "../src/utility/database/libsql/database.js";
import { applyLibSqlSchemaStatement, type DatabaseConnection } from "../src/utility/database/libsql/libsql-client.js";
import { toLibSqlSql } from "../src/utility/database/libsql/sql.js";

test("libSQL initializes the v3 schema and keeps guild data isolated", async () => {
  const directory = await mkdtemp(join(tmpdir(), "lemegeton-libsql-schema-"));
  const config = { path: join(directory, "bot.db"), primaryGuildId: null };
  try {
    await initDatabase(config);
    const tables = await query<{ name: string }>(
      "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ('users','guild_retention_settings','media_assets','media_relationship_graph','media_timeline_provider_events','timeline_correction_requests','industry_directory_pins','industry_correction_requests','identify_cases','identify_candidates','identify_evidence','identify_candidate_votes','identify_case_reports','exchange_requests','exchange_candidates','relay_chains','relay_members','relay_contributions','workshop_projects','workshop_sections','workshop_revisions','time_capsules','time_capsule_contributions','council_proposals','council_amendments','council_ballots','council_votes','expeditions','expedition_stages','expedition_participants','expedition_submissions','casebook_cases','casebook_evidence','casebook_theories') ORDER BY name",
    );
    assert.deepEqual(tables.map(row => row.name), [
      "casebook_cases", "casebook_evidence", "casebook_theories",
      "council_amendments", "council_ballots", "council_proposals", "council_votes",
      "expedition_participants", "expedition_stages", "expedition_submissions", "expeditions",
      "exchange_candidates", "exchange_requests", "guild_retention_settings",
      "identify_candidate_votes", "identify_candidates", "identify_case_reports", "identify_cases", "identify_evidence",
      "industry_correction_requests", "industry_directory_pins", "media_assets", "media_relationship_graph",
      "media_timeline_provider_events", "relay_chains", "relay_contributions", "relay_members",
      "time_capsule_contributions", "time_capsules", "timeline_correction_requests", "users",
      "workshop_projects", "workshop_revisions", "workshop_sections",
    ]);

    await query(
      "INSERT INTO users (discord_id, guild_id, username) VALUES ($1,$2,$3),($1,$4,$3)",
      ["123456789012345678", "111111111111111111", "member", "222222222222222222"],
    );
    const firstGuild = await queryOne<{ discord_id: string; guild_id: string }>(
      "SELECT discord_id, guild_id FROM users WHERE guild_id = $1",
      ["111111111111111111"],
    );
    const secondGuild = await queryOne<{ discord_id: string; guild_id: string }>(
      "SELECT discord_id, guild_id FROM users WHERE guild_id = $1",
      ["222222222222222222"],
    );
    assert.equal(firstGuild?.discord_id, "123456789012345678");
    assert.equal(secondGuild?.discord_id, "123456789012345678");
    assert.notEqual(firstGuild?.guild_id, secondGuild?.guild_id);

    await assert.rejects(transaction(async client => {
      await client.query(
        "INSERT INTO guild_language_settings (guild_id, language_code, updated_by) VALUES ($1,$2,$3)",
        ["111111111111111111", "en", "123456789012345678"],
      );
      throw new Error("rollback-check");
    }), /rollback-check/);
    assert.equal(await queryOne("SELECT guild_id FROM guild_language_settings WHERE guild_id = $1", ["111111111111111111"]), null);

    await query(
      `INSERT INTO media_relationship_graph
        (source_title,source_title_key,source_category,source_url,target_title,target_title_key,target_category,target_url,
         relationship_type,source_kind,source_label,guild_id)
       VALUES ($1,$2,'ANIME',$3,$4,$5,'MOVIE',$6,'adaptation','provider','Provider metadata',$7)`,
      [
        "Source anime", "source anime", "https://anilist.co/anime/12345/source",
        "Target film", "target film", "https://www.themoviedb.org/movie/67890-target",
        "111111111111111111",
      ],
    );
    assert.equal(await backfillAtlasProviderIdentities(), 1);
    const relationship = await queryOne<{
      source_provider: string | null; source_provider_id: string | null;
      target_provider: string | null; target_provider_id: string | null;
    }>(
      "SELECT source_provider,source_provider_id,target_provider,target_provider_id FROM media_relationship_graph WHERE guild_id = $1",
      ["111111111111111111"],
    );
    assert.deepEqual(relationship, {
      source_provider: "anilist:anime",
      source_provider_id: "12345",
      target_provider: "tmdb:movie",
      target_provider_id: "67890",
    });
  } finally {
    await closeDatabase();
    await rm(directory, { recursive: true, force: true });
  }
});

test("libSQL skips PostgreSQL procedural migration blocks", async () => {
  let queries = 0;
  const database = {
    query: async () => {
      queries += 1;
      return { rows: [], rowCount: 0, lastInsertRowid: "0" };
    },
    release: () => undefined,
  } as unknown as DatabaseConnection;

  await applyLibSqlSchemaStatement(
    "DO $candidate_status$ DECLARE constraint_definition TEXT; BEGIN SELECT 1; END; $candidate_status$",
    database,
  );
  assert.equal(queries, 0);
});

test("libSQL schema translation removes PostgreSQL array containment checks", () => {
  const translated = toLibSqlSql(
    "CREATE TABLE music_trackers (providers TEXT[] NOT NULL CHECK (providers <@ ARRAY['spotify','youtube','soundcloud']::TEXT[]))",
    true,
  );
  assert.doesNotMatch(translated, /<@|@>/);
  assert.match(translated, /providers TEXT NOT NULL/);
});
