import test from "node:test";
import assert from "node:assert/strict";
import { IgdbClient, parseIgdbCompany, parseIgdbCompanyCredits } from "../helpers/integration/igdb.js";

const companyRecord = {
  id: 42,
  name: "Example Studio",
  slug: "example-studio",
  description: "A game development and publishing company.",
  country: 1,
  logo: { url: "//images.igdb.com/igdb/image/upload/t_logo_med/co1234.png" },
  websites: [
    { url: "https://example.com/" },
    { url: "javascript:alert(1)" },
    { url: "http://insecure.example/" },
  ],
};

test("IGDB company normalization keeps stable IDs and only safe source assets and websites", () => {
  const company = parseIgdbCompany(companyRecord);
  assert.ok(company);
  assert.equal(company.id, 42);
  assert.equal(company.sourceUrl, "https://www.igdb.com/companies/example-studio");
  assert.equal(company.logo, "https://images.igdb.com/igdb/image/upload/t_logo_med/co1234.png");
  assert.deepEqual(company.websites, ["https://example.com/"]);
  assert.equal(parseIgdbCompany({ id: "42", name: "Invalid" }), null);
});

test("IGDB company credits preserve the actual developer and publisher relationship", () => {
  const credits = parseIgdbCompanyCredits([
    {
      developer: true,
      publisher: false,
      game: { id: 7, name: "Example Game", slug: "example-game", first_release_date: 1_700_000_000 },
    },
    {
      developer: false,
      publisher: true,
      game: { id: 7, name: "Example Game", slug: "example-game", first_release_date: 1_700_000_000 },
    },
    {
      developer: false,
      publisher: false,
      game: { id: 8, name: "Unattributed Game", slug: "unattributed-game" },
    },
  ]);
  assert.equal(credits.length, 1);
  assert.equal(credits[0]?.gameId, 7);
  assert.deepEqual(credits[0]?.roles, ["Developer", "Publisher"]);
  assert.equal(credits[0]?.sourceUrl, "https://www.igdb.com/games/example-game");
  assert.equal(credits[0]?.releaseDate, "2023-11-14");
});

test("IGDB Creator Explorer uses documented Company and Involved Company endpoints", async () => {
  const requests: Array<{ url: string; body: string }> = [];
  const fetcher: typeof fetch = async (input, init) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    const body = typeof init?.body === "string" ? init.body : "";
    requests.push({ url, body });
    if (url.startsWith("https://id.twitch.tv/oauth2/token")) {
      return new Response(JSON.stringify({ access_token: "test-token", expires_in: 3600 }), { status: 200 });
    }
    if (url.endsWith("/companies") && body.includes('search "Example Studio"')) {
      return new Response(JSON.stringify([companyRecord]), { status: 200 });
    }
    if (url.endsWith("/companies") && body.includes("where id = 42")) {
      return new Response(JSON.stringify([companyRecord]), { status: 200 });
    }
    if (url.endsWith("/involved_companies") && body.includes("where company = 42")) {
      return new Response(JSON.stringify([{
        developer: true,
        publisher: false,
        porting: false,
        supporting: false,
        game: { id: 7, name: "Example Game", slug: "example-game" },
      }]), { status: 200 });
    }
    return new Response("Unexpected IGDB request", { status: 404 });
  };
  const client = new IgdbClient("test-client", "test-secret", fetcher);
  const matches = await client.searchCompanies("Example Studio");
  assert.equal(matches.length, 1);
  assert.equal(matches[0]?.id, 42);
  const explorer = await client.getCompanyExplorer(42);
  assert.equal(explorer?.company.name, "Example Studio");
  assert.equal(explorer?.credits[0]?.title, "Example Game");
  assert.deepEqual(explorer?.credits[0]?.roles, ["Developer"]);
  assert.ok(requests.some((request) => request.url.endsWith("/companies") && request.body.includes("fields id,name,slug,description,country,logo.url,websites.url")));
  assert.ok(requests.some((request) => request.url.endsWith("/involved_companies") && request.body.includes("fields developer,publisher,porting,supporting,game.id,game.name")));
  assert.ok(requests.every((request) => request.url.startsWith("https://id.twitch.tv/oauth2/token")
    || request.url.startsWith("https://api.igdb.com/v4/")));
});
