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
        { key: "/books/OL22597282M", title: "Dune", isbn_10: ["0441172717", "0123456788"], isbn_13: [isbn, "9780441172718"], publish_date: "1987" },
        { key: "/books/OL123456M", title: "Dune", isbn_13: [isbn], edition_name: "Ace edition" },
      ],
    }));
  };
  const family = await new OpenLibraryClient(fetcher, 0).findEditionFamily(isbn);
  assert.equal(family?.workId, "OL893414W");
  assert.equal(family?.editionCount, 2);
  assert.equal(family?.editions.length, 2);
  assert.equal(family?.editions[1]?.editionName, "Ace edition");
  assert.deepEqual(family?.editions[0]?.isbn10, ["0441172717"]);
  assert.deepEqual(family?.editions[0]?.isbn13, [isbn]);
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

test("Open Library title search returns work metadata and caches the same user query", async () => {
  const requests: string[] = [];
  const fetcher: typeof fetch = async input => {
    requests.push(String(input));
    return new Response(JSON.stringify({
      docs: [{
        key: "/works/OL123W",
        title: "The Left Hand of Darkness",
        alternate_titles: ["The Left Hand of Darkness", "Winter's King", "Le Guin's Winter World"],
        author_name: ["Ursula K. Le Guin"],
        first_publish_year: 1969,
        edition_count: 24,
        subject: ["Science fiction", "Gender"],
        publisher: ["Ace Books"],
        language: ["/languages/eng"],
        isbn: ["0441478123", "0123456788", "9780441478125", "9780441172718"],
        cover_i: 101,
      }],
    }), { status: 200, headers: { "content-type": "application/json" } });
  };
  const client = new OpenLibraryClient(fetcher, 0);
  const first = await client.searchTitle("The Left Hand of Darkness");
  const second = await client.searchTitle("The Left Hand of Darkness");
  assert.equal(requests.length, 1);
  const url = new URL(requests[0]!);
  assert.equal(url.searchParams.get("title"), "The Left Hand of Darkness");
  assert.equal(url.searchParams.get("limit"), "10");
  assert.equal(first[0]?.workId, "OL123W");
  assert.equal(first[0]?.authors[0], "Ursula K. Le Guin");
  assert.deepEqual(first[0]?.alternateTitles, ["Winter's King", "Le Guin's Winter World"]);
  assert.deepEqual(first[0]?.isbn10, ["0441478123"]);
  assert.deepEqual(first[0]?.isbn13, ["9780441478125"]);
  assert.equal(first[0]?.coverUrl, "https://covers.openlibrary.org/b/id/101-M.jpg");
  assert.deepEqual(second, first);
});

test("Open Library subject search ignores non-work identifiers", async () => {
  let requested = "";
  const client = new OpenLibraryClient(async input => {
    requested = String(input);
    return new Response(JSON.stringify({
      works: [
        { key: "/works/OL987W", title: "A Fantasy Chronicle", authors: [{ name: "A. Author" }], edition_count: 5 },
        { key: "/books/OL123M", title: "Invalid edition result" },
      ],
    }), { status: 200 });
  }, 0);
  const results = await client.searchBySubject("Science Fiction");
  assert.match(requested, /\/subjects\/science-fiction\.json\?limit=10/);
  assert.equal(results.length, 1);
  assert.equal(results[0]?.workId, "OL987W");
});
