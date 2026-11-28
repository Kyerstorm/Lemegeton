import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { closeDatabase, initDatabase } from "../src/utility/database/libsql/database.js";
import {
  createIndustryCorrectionRequest,
  createIndustryIdentityLinkRequest,
  getIndustryIdentityLinkRequest,
  listApprovedIndustryIdentityLinks,
  listPendingIndustryIdentityLinks,
  listIndustryPins,
  pinIndustryOrganization,
  removeIndustryPin,
  reviewIndustryCorrectionRequest,
  reviewIndustryIdentityLinkRequest,
} from "../helpers/media/industry-directory.js";

test("industry pins are unique and isolated by guild", async () => {
  const directory = await mkdtemp(join(tmpdir(), "lemegeton-industry-directory-"));
  await initDatabase({ path: join(directory, "bot.db"), primaryGuildId: null });
  const base = {
    provider: "igdb:company",
    providerId: "123",
    displayName: "Example Studio",
    category: "game-company",
    sourceUrl: "https://www.igdb.com/companies/example",
    pinnedBy: "333333333333333333",
  };
  try {
    assert.equal(await pinIndustryOrganization({ ...base, guildId: "111111111111111111" }), true);
    assert.equal(await pinIndustryOrganization({ ...base, guildId: "111111111111111111" }), false);
    assert.equal(await pinIndustryOrganization({ ...base, guildId: "222222222222222222" }), true);
    assert.equal((await listIndustryPins("111111111111111111")).length, 1);
    assert.equal((await listIndustryPins("222222222222222222")).length, 1);
    const pins = await listIndustryPins("111111111111111111");
    assert.equal(pins[0]?.providerId, "123");
    assert.equal(await removeIndustryPin("111111111111111111", pins[0]!.id), true);
    assert.equal((await listIndustryPins("111111111111111111")).length, 0);
    assert.equal((await listIndustryPins("222222222222222222")).length, 1);
  } finally {
    await closeDatabase();
    await rm(directory, { recursive: true, force: true });
  }
});

test("industry correction intake requires source evidence on HTTPS", async () => {
  const directory = await mkdtemp(join(tmpdir(), "lemegeton-industry-correction-"));
  await initDatabase({ path: join(directory, "bot.db"), primaryGuildId: null });
  try {
    const id = await createIndustryCorrectionRequest({
      guildId: "111111111111111111",
      provider: "tmdb:company",
      providerId: "42",
      organizationName: "Example Pictures",
      fieldName: "homepage",
      proposedValue: "https://example.com/",
      evidenceUrl: "https://example.com/about",
      createdBy: "333333333333333333",
    });
    assert.ok(id);
    await assert.rejects(() => createIndustryCorrectionRequest({
      guildId: "111111111111111111",
      provider: "tmdb:company",
      providerId: "42",
      organizationName: "Example Pictures",
      fieldName: "homepage",
      proposedValue: "http://example.com/",
      evidenceUrl: "http://example.com/about",
      createdBy: "333333333333333333",
    }), /HTTPS/);
  } finally {
    await closeDatabase();
    await rm(directory, { recursive: true, force: true });
  }
});

test("industry corrections and provider identity links require guild-scoped moderator review", async () => {
  const directory = await mkdtemp(join(tmpdir(), "lemegeton-industry-review-"));
  await initDatabase({ path: join(directory, "bot.db"), primaryGuildId: null });
  try {
    const correctionId = await createIndustryCorrectionRequest({
      guildId: "111111111111111111",
      provider: "tmdb:company",
      providerId: "42",
      organizationName: "Example Pictures",
      fieldName: "parent company",
      proposedValue: "Example Group",
      evidenceUrl: "https://example.com/corporate-history",
      createdBy: "222222222222222222",
    });
    assert.ok(correctionId);
    await assert.rejects(() => reviewIndustryCorrectionRequest({
      guildId: "111111111111111111",
      requestId: correctionId!,
      reviewerId: "222222222222222222",
      decision: "approved",
    }), /cannot review their own/);
    assert.equal(await reviewIndustryCorrectionRequest({
      guildId: "111111111111111111",
      requestId: correctionId!,
      reviewerId: "333333333333333333",
      decision: "approved",
      note: "The linked corporate filing supports this.",
    }), true);
    assert.equal(await reviewIndustryCorrectionRequest({
      guildId: "222222222222222222",
      requestId: correctionId!,
      reviewerId: "444444444444444444",
      decision: "rejected",
    }), false);

    const linkId = await createIndustryIdentityLinkRequest({
      guildId: "111111111111111111",
      sourceProvider: "tmdb:company",
      sourceProviderId: "42",
      sourceName: "Example Pictures",
      sourceUrl: "https://www.themoviedb.org/company/42",
      targetProvider: "wikidata:entity",
      targetProviderId: "Q12345",
      targetName: "Example Pictures",
      targetUrl: "https://www.wikidata.org/wiki/Q12345",
      evidenceUrl: "https://example.com/company-identifiers",
      createdBy: "555555555555555555",
    });
    assert.ok(linkId);
    const pending = await listPendingIndustryIdentityLinks("111111111111111111");
    assert.equal(pending.length, 1);
    assert.equal((await listPendingIndustryIdentityLinks("222222222222222222")).length, 0);
    const request = await getIndustryIdentityLinkRequest("111111111111111111", linkId!);
    assert.equal(request?.target_provider_id, "Q12345");
    assert.equal(await reviewIndustryIdentityLinkRequest({
      guildId: "111111111111111111",
      requestId: linkId!,
      reviewerId: "555555555555555555",
      decision: "approved",
    }), false);
    assert.equal(await reviewIndustryIdentityLinkRequest({
      guildId: "111111111111111111",
      requestId: linkId!,
      reviewerId: "666666666666666666",
      decision: "approved",
      note: "The official company page lists the Wikidata identifier.",
    }), true);
    const links = await listApprovedIndustryIdentityLinks({
      guildId: "111111111111111111",
      provider: "tmdb:company",
      providerId: "42",
    });
    assert.equal(links.length, 1);
    assert.equal(links[0]?.provider, "wikidata:entity");
    assert.equal(links[0]?.provider_id, "Q12345");
    assert.equal((await listApprovedIndustryIdentityLinks({
      guildId: "222222222222222222",
      provider: "tmdb:company",
      providerId: "42",
    })).length, 0);
  } finally {
    await closeDatabase();
    await rm(directory, { recursive: true, force: true });
  }
});
