import test from "node:test";
import assert from "node:assert/strict";
import { CrossrefClient, normalizeBibliographicIsbn, parseCrossrefBookMatches } from "../helpers/integration/crossref.js";

const isbn = "9780306406157";

test("ISBN normalizer accepts hyphenated 10 and 13 digit identifiers", () => {
  assert.equal(normalizeBibliographicIsbn("978-0-306-40615-7"), isbn);
  assert.equal(normalizeBibliographicIsbn("0-306-40615-2"), "0306406152");
  assert.equal(normalizeBibliographicIsbn("not-an-isbn"), null);
});

test("Crossref matches only records that explicitly contain the requested ISBN", () => {
  const matches = parseCrossrefBookMatches({
    message: { items: [
      { DOI: "10.1234/book.1", title: ["Example Book"], type: "book", ISBN: ["978-0-306-40615-7"],
        editor: [{ given: "Ari", family: "Editor" }], translator: [{ name: "T. Translator", ORCID: "https://orcid.org/0000-0002-1825-0097" }] },
      { DOI: "10.1234/book.2", title: ["Different ISBN"], ISBN: ["9781111111111"], editor: [{ name: "Wrong match" }] },
    ] },
  }, isbn);
  assert.equal(matches.length, 1);
  assert.equal(matches[0]?.title, "Example Book");
  assert.deepEqual(matches[0]?.editors.map(item => item.name), ["Ari Editor"]);
  assert.deepEqual(matches[0]?.translators.map(item => item.name), ["T. Translator"]);
  assert.equal(matches[0]?.sourceUrl, "https://doi.org/10.1234/book.1");
});

test("Crossref client sends the exact ISBN filter and retains provider failure", async () => {
  let requested = "";
  const fetcher: typeof fetch = async (input) => {
    requested = String(input);
    return new Response(JSON.stringify({ message: { items: [] } }), { status: 200 });
  };
  const client = new CrossrefClient(fetcher);
  assert.deepEqual(await client.findByIsbn(isbn), []);
  assert.match(requested, /filter=isbn%3A9780306406157/);
  const failing = new CrossrefClient(async () => new Response("failed", { status: 503 }));
  await assert.rejects(() => failing.findByIsbn(isbn), /HTTP 503/);
});

test("bibliographic ISBN normalization validates ISBN-10 and ISBN-13 checksums", () => {
  assert.equal(normalizeBibliographicIsbn("ISBN-10: 0-441-17271-7"), "0441172717");
  assert.equal(normalizeBibliographicIsbn("978-0-441-17271-9"), "9780441172719");
  assert.equal(normalizeBibliographicIsbn("0441172718"), null);
  assert.equal(normalizeBibliographicIsbn("9780441172718"), null);
});
