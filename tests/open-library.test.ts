import test from "node:test";
import assert from "node:assert/strict";
import { OpenLibraryClient } from "../helpers/integration/open-library.js";

const isbn = "9780441172719";

test("Open Library links an exact ISBN edition to the editions of its single catalogue work", async () => {
  const requests: string[] = [];
  const fetcher: typeof fetch = async (input) => {
    const url = String(input);
    requests.push(url);
    if (url.endsWith("/isbn/" + isbn + ".json")) {
      return new Response(JSON.stringify({ key: "/books/OL22597282M", works: [{ key: "/works/OL893414W" }] }));
    }
    return new Response(JSON.stringify({
      size: 2,
      entries: [
        { key: "/books/OL22597282M", title: "Dune", isbn_10: ["0441172717"], isbn_13: [isbn], publish_date: "1987" },
        { key: "/books/OL123456M", title: "Dune", isbn_13: [isbn], edition_name: "Ace edition" },
      ],
    }));
  };
  const family = await new OpenLibraryClient(fetcher, 0).findEditionFamily(isbn);
  assert.equal(family?.workId, "OL893414W");
  assert.equal(family?.editionCount, 2);
  assert.equal(family?.editions.length, 2);
  assert.equal(family?.editions[1]?.editionName, "Ace edition");
  assert.equal(requests.length, 2);
  assert.match(requests[1]!, /\/works\/OL893414W\/editions\.json/);
});

test("Open Library does not invent a work family for ambiguous ISBN records", async () => {
  let calls = 0;
  const fetcher: typeof fetch = async () => {
    calls++;
    return new Response(JSON.stringify({
      works: [{ key: "/works/OL1W" }, { key: "/works/OL2W" }],
    }));
  };
  const family = await new OpenLibraryClient(fetcher, 0).findEditionFamily(isbn);
  assert.equal(family, null);
  assert.equal(calls, 1);
});
