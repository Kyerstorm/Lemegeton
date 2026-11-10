import test from "node:test";
import assert from "node:assert/strict";
import { GoogleBooksClient } from "../helpers/integration/google-books.js";

async function withFetch<T>(
  implementation: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>,
  run: () => Promise<T>,
): Promise<T> {
  const original = globalThis.fetch;
  globalThis.fetch = implementation as typeof fetch;
  try {
    return await run();
  } finally {
    globalThis.fetch = original;
  }
}

test("Google Books search normalizes volume metadata and source URLs", async () => {
  await withFetch(async input => {
    const url = new URL(String(input));
    assert.equal(url.origin + url.pathname, "https://www.googleapis.com/books/v1/volumes");
    assert.equal(url.searchParams.get("q"), "Dune");
    assert.equal(url.searchParams.get("maxResults"), "10");
    assert.equal(url.searchParams.get("printType"), "books");
    assert.equal(url.searchParams.get("key"), "fixture-key");
    return new Response(JSON.stringify({
      items: [
        {
          id: "dune-id",
          volumeInfo: {
            title: "Dune",
            authors: ["Frank Herbert", 42],
            publisher: "Ace",
            publishedDate: "1965",
            description: "A science-fiction novel.",
            pageCount: 896,
            categories: ["Fiction"],
            industryIdentifiers: [
              { type: "ISBN_13", identifier: "9780441172719" },
            ],
            imageLinks: { thumbnail: "http://books.google.test/dune.jpg" },
          },
        },
        { id: "incomplete", volumeInfo: { authors: ["No title"] } },
        null,
      ],
    }), { status: 200, headers: { "content-type": "application/json" } });
  }, async () => {
    const [book] = await new GoogleBooksClient("fixture-key").search(" Dune ");
    assert.deepEqual(book, {
      id: "dune-id",
      title: "Dune",
      authors: ["Frank Herbert"],
      publisher: "Ace",
      publishedDate: "1965",
      description: "A science-fiction novel.",
      pageCount: 896,
      categories: ["Fiction"],
      isbn: "9780441172719",
      sourceUrl: "https://books.google.com/books?id=dune-id",
      image: "https://books.google.test/dune.jpg",
    });
  });
});

test("Google Books subject search normalizes whitespace and rejects invalid input", async () => {
  await withFetch(async input => {
    const url = new URL(String(input));
    assert.equal(url.searchParams.get("q"), "subject:Science Fiction");
    return new Response(JSON.stringify({ items: [] }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }, async () => {
    const client = new GoogleBooksClient();
    assert.deepEqual(await client.searchBySubject("  Science   Fiction  "), []);
    await assert.rejects(client.searchBySubject("   "), /valid non-empty category/);
    await assert.rejects(client.searchBySubject('sci"fi'), /valid non-empty category/);
  });
});

test("Google Books returns a useful error for provider failures", async () => {
  await withFetch(async () => new Response("unavailable", { status: 503 }), async () => {
    await assert.rejects(new GoogleBooksClient().search("Dune"), /Google Books returned HTTP 503/);
  });
});
