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
    assert.equal(url.searchParams.get("projection"), "full");
    assert.equal(url.searchParams.get("key"), "fixture-key");
    return new Response(JSON.stringify({
      items: [
        {
          id: "dune-id",
          volumeInfo: {
            title: "Dune",
            subtitle: "A Novel",
            authors: ["Frank Herbert", 42],
            publisher: "Ace",
            publishedDate: "1965",
            description: "A science-fiction novel.",
            pageCount: 896,
            categories: ["Fiction"],
            mainCategory: "Fiction",
            language: "en",
            printType: "BOOK",
            industryIdentifiers: [
              { type: "ISBN_10", identifier: "0441172717" },
              { type: "ISBN_13", identifier: "9780441172719" },
            ],
            seriesInfo: {
              shortSeriesBookTitle: "Dune",
              bookDisplayNumber: "1",
              volumeSeries: [{ orderNumber: 1, seriesId: "dune-series", seriesBookType: "COLLECTED_EDITION" }],
            },
            previewLink: "https://books.google.com/books?id=dune-id&printsec=frontcover",
            infoLink: "https://books.google.com/books?id=dune-id",
            imageLinks: { thumbnail: "http://books.google.com/books/content?id=dune-id" },
          },
          accessInfo: {
            country: "IE", viewability: "PARTIAL", publicDomain: false,
            webReaderLink: "https://books.google.com/books?id=dune-id&printsec=frontcover",
            pdf: { isAvailable: false }, epub: { isAvailable: true },
          },
          saleInfo: { country: "IE", saleability: "FOR_SALE", isEbook: true, buyLink: "https://play.google.com/store/books/details?id=dune-id" },
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
      subtitle: "A Novel",
      authors: ["Frank Herbert"],
      publisher: "Ace",
      publishedDate: "1965",
      description: "A science-fiction novel.",
      pageCount: 896,
      categories: ["Fiction"],
      mainCategory: "Fiction",
      language: "en",
      printType: "BOOK",
      isbn: "9780441172719",
      isbn10: "0441172717",
      isbn13: "9780441172719",
      seriesBookTitle: "Dune",
      seriesDisplayNumber: "1",
      seriesOrder: 1,
      seriesId: "dune-series",
      seriesBookType: "COLLECTED_EDITION",
      sourceUrl: "https://books.google.com/books?id=dune-id",
      previewUrl: "https://books.google.com/books?id=dune-id&printsec=frontcover",
      infoUrl: "https://books.google.com/books?id=dune-id",
      image: "https://books.google.com/books/content?id=dune-id",
      catalogueRegion: "IE",
      viewability: "PARTIAL",
      webReaderUrl: "https://books.google.com/books?id=dune-id&printsec=frontcover",
      pdfAvailable: false,
      epubAvailable: true,
      publicDomain: false,
      saleability: "FOR_SALE",
      isEbook: true,
      buyUrl: "https://play.google.com/store/books/details?id=dune-id",
    });
  });
});

test("Google Books falls back from ISBN-13 to ISBN-10 and ignores unsafe edition links", async () => {
  await withFetch(async () => new Response(JSON.stringify({
    items: [{
      id: "legacy-isbn",
      volumeInfo: {
        title: "Legacy Edition",
        industryIdentifiers: [{ type: "ISBN_10", identifier: "0306406152" }],
        previewLink: "javascript:alert(1)",
        infoLink: "https://books.google.com/books?id=legacy-isbn",
        imageLinks: { thumbnail: "https://not-google.example/image.jpg" },
      },
    }],
  }), { status: 200, headers: { "content-type": "application/json" } }), async () => {
    const [book] = await new GoogleBooksClient().search("Legacy Edition");
    assert.equal(book?.isbn, "0306406152");
    assert.equal(book?.isbn10, "0306406152");
    assert.equal(book?.isbn13, null);
    assert.equal(book?.previewUrl, null);
    assert.equal(book?.infoUrl, "https://books.google.com/books?id=legacy-isbn");
    assert.equal(book?.image, null);
    assert.equal(book?.seriesOrder, null);
  });
});

test("Google Books discards provider identifiers with invalid checksums", async () => {
  await withFetch(async () => new Response(JSON.stringify({ items: [{
    id: "bad-isbns",
    volumeInfo: {
      title: "Bad ISBN fixture",
      industryIdentifiers: [
        { type: "ISBN_13", identifier: "9780441172718" },
        { type: "ISBN_10", identifier: "0123456789" },
      ],
    },
  }] }), { status: 200, headers: { "content-type": "application/json" } }), async () => {
    const [book] = await new GoogleBooksClient().search("Bad ISBN fixture");
    assert.equal(book?.isbn, null);
    assert.equal(book?.isbn10, null);
    assert.equal(book?.isbn13, null);
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

test("Google Books exact ISBN lookup validates the ISBN and filters non-matching editions", async () => {
  await withFetch(async input => {
    const url = new URL(String(input));
    assert.equal(url.searchParams.get("q"), "isbn:9780441172719");
    return new Response(JSON.stringify({
      items: [
        { id: "dune-edition", volumeInfo: {
          title: "Dune", industryIdentifiers: [
            { type: "ISBN_13", identifier: "9780441172719" },
            { type: "ISBN_10", identifier: "0441172717" },
          ],
        } },
        { id: "other-edition", volumeInfo: {
          title: "Dune (different edition)",
          industryIdentifiers: [{ type: "ISBN_13", identifier: "9780000000002" }],
        } },
      ],
    }), { status: 200, headers: { "content-type": "application/json" } });
  }, async () => {
    const results = await new GoogleBooksClient().findEdition("ISBN-13: 978-0-441-17271-9");
    assert.equal(results.length, 1);
    assert.equal(results[0]?.id, "dune-edition");
    assert.equal(results[0]?.isbn13, "9780441172719");
  });
});

test("Google Books volume lookup uses the stable volume ID endpoint", async () => {
  await withFetch(async input => {
    const url = new URL(String(input));
    assert.equal(url.origin + url.pathname, "https://www.googleapis.com/books/v1/volumes/dune-volume-id");
    assert.equal(url.searchParams.get("key"), "fixture-key");
    return new Response(JSON.stringify({
      id: "dune-volume-id",
      volumeInfo: {
        title: "Dune",
        industryIdentifiers: [{ type: "ISBN_13", identifier: "9780441172719" }],
      },
    }), { status: 200, headers: { "content-type": "application/json" } });
  }, async () => {
    const result = await new GoogleBooksClient("fixture-key").findEdition("dune-volume-id");
    assert.equal(result[0]?.id, "dune-volume-id");
    assert.equal(result[0]?.title, "Dune");
  });
});

test("Google Books exact edition lookup rejects invalid ISBN checksums and malformed identifiers", async () => {
  const client = new GoogleBooksClient();
  await assert.rejects(client.findEdition("9780441172718"), /invalid checksum/);
  await assert.rejects(client.findEdition("not an identifier"), /valid ISBN-10, ISBN-13 or Google Books volume ID/);
});


test("Google Books regional search sends a validated country code", async () => {
  await withFetch(async input => {
    const url = new URL(String(input));
    assert.equal(url.searchParams.get("country"), "IE");
    return new Response(JSON.stringify({ items: [] }), { status: 200, headers: { "content-type": "application/json" } });
  }, async () => {
    assert.deepEqual(await new GoogleBooksClient().search("Dune", "ie"), []);
    await assert.rejects(new GoogleBooksClient().search("Dune", "Ireland"), /two-letter country code/);
  });
});
