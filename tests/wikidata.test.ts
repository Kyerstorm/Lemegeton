import test from "node:test";
import assert from "node:assert/strict";
import {
  parseWikidataEntitySearch,
  parseWikidataRelations,
  WikidataClient,
} from "../helpers/integration/wikidata.js";

test("Wikidata entity search keeps valid QIDs and stable entity links", () => {
  const results = parseWikidataEntitySearch({ search: [
    { id: "Q42", label: "Douglas Adams", description: "English writer" },
    { id: "Q42", label: "Duplicate" },
    { id: "not-a-qid", label: "Invalid" },
    { id: "Q7", label: " " },
  ] });
  assert.deepEqual(results, [{
    id: "Q42",
    label: "Douglas Adams",
    description: "English writer",
    url: "https://www.wikidata.org/wiki/Q42",
  }]);
});

test("Wikidata relation parser preserves typed properties and rejects malformed URIs", () => {
  const results = parseWikidataRelations({ results: { bindings: [
    {
      subject: { value: "http://www.wikidata.org/entity/Q1" },
      property: { value: "http://www.wikidata.org/prop/direct/P155" },
      object: { value: "http://www.wikidata.org/entity/Q2" },
      subjectLabel: { value: "Later work" },
      objectLabel: { value: "Earlier work" },
    },
    {
      subject: { value: "https://evil.example/entity/Q3" },
      property: { value: "http://www.wikidata.org/prop/direct/P155" },
      object: { value: "http://www.wikidata.org/entity/Q4" },
    },
  ] } }, "sequence");
  assert.equal(results.length, 1);
  assert.equal(results[0]?.propertyId, "P155");
  assert.equal(results[0]?.subjectLabel, "Later work");
  assert.equal(results[0]?.kind, "sequence");
});

test("Wikidata client uses the Query Service v2 endpoint and fixed property sets", async () => {
  const requests: URL[] = [];
  const fetcher: typeof fetch = async input => {
    const url = new URL(String(input));
    requests.push(url);
    return new Response(JSON.stringify({ results: { bindings: [] } }), {
      status: 200,
      headers: { "content-type": "application/sparql-results+json" },
    });
  };
  const client = new WikidataClient(fetcher, 0);
  assert.deepEqual(await client.sequenceRelations("Q42"), []);
  assert.deepEqual(await client.organizationRelations("Q43"), []);
  assert.equal(requests[0]?.hostname, "query-next.wikidata.org");
  assert.match(requests[0]?.searchParams.get("query") ?? "", /wdt:P155 wdt:P156 wdt:P179/);
  assert.match(requests[1]?.searchParams.get("query") ?? "", /wdt:P749 wdt:P355/);
  await assert.rejects(() => client.sequenceRelations("Q42 ; SERVICE"), /valid QID/);
});

test("Wikidata client sends a bounded Wikibase entity search", async () => {
  let requested = new URL("https://example.com");
  const fetcher: typeof fetch = async input => {
    requested = new URL(String(input));
    return new Response(JSON.stringify({ search: [{ id: "Q42", label: "Douglas Adams" }] }), { status: 200 });
  };
  const client = new WikidataClient(fetcher, 0);
  const results = await client.searchEntities("  Douglas   Adams  ");
  assert.equal(results[0]?.id, "Q42");
  assert.equal(requested.hostname, "www.wikidata.org");
  assert.equal(requested.searchParams.get("limit"), "10");
  assert.equal(requested.searchParams.get("action"), "wbsearchentities");
});
