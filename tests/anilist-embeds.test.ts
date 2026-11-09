import test from "node:test";
import assert from "node:assert/strict";
import { AniListClient } from "../helpers/anilist.js";
import { parseAniListUrl } from "../helpers/embeds/anilist.js";
import {
  buildErrorEmbed,
  buildInfoEmbed,
  buildMediaEmbed,
  buildRelationsEmbeds,
  buildStatsEmbed,
  buildSuccessEmbed,
  buildTagsEmbed,
  buildTrendingEmbed,
  buildUserFavoritesEmbed,
  buildUserProfileEmbed,
} from "../helpers/embeds/core.js";

test("AniList URL parser recognizes media and supported profile sections", () => {
  assert.deepEqual(parseAniListUrl("https://anilist.co/anime/123/example-title"), {
    kind: "media", id: 123, type: "ANIME",
  });
  assert.deepEqual(parseAniListUrl("https://www.anilist.co/manga/456"), {
    kind: "media", id: 456, type: "MANGA",
  });
  assert.deepEqual(parseAniListUrl("https://anilist.co/user/VireonNoctis/"), {
    kind: "user", username: "VireonNoctis", section: "overview",
  });
  assert.equal(parseAniListUrl("https://anilist.co/user/example/stats")?.kind, "user");
  assert.equal(parseAniListUrl("https://anilist.co/user/example/statistics")?.kind, "user");
  assert.equal(parseAniListUrl("https://anilist.co/user/example/favorites")?.kind, "user");
  assert.equal(parseAniListUrl("https://anilist.co/user/example/activity")?.kind, "user");
});

test("AniList URL parser ignores personal list routes and unsafe or malformed URLs", () => {
  for (const route of ["animelist", "anime", "anime-list", "mangalist", "manga", "manga-list"]) {
    assert.equal(parseAniListUrl("https://anilist.co/user/example/" + route), null);
  }
  assert.equal(parseAniListUrl("https://evil.example/anime/1"), null);
  assert.equal(parseAniListUrl("http://anilist.co/anime/1"), null);
  assert.equal(parseAniListUrl("https://anilist.co/anime/0"), null);
  assert.equal(parseAniListUrl("https://anilist.co/anime/not-a-number"), null);
  assert.equal(parseAniListUrl("not a URL"), null);
});

test("AniList detail query normalizes the sections needed by the media embed family", async () => {
  const payload = {
    data: {
      Media: {
        id: 123,
        type: "ANIME",
        isAdult: false,
        title: { romaji: "Example Anime", english: "Example", native: "例" },
        description: "<p>Synopsis text.</p>",
        siteUrl: "https://anilist.co/anime/123/example",
        coverImage: { large: "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/123.jpg" },
        bannerImage: "https://s4.anilist.co/file/anilistcdn/media/anime/banner/123.jpg",
        averageScore: 87,
        status: "FINISHED",
        format: "TV",
        startDate: { year: 2024, month: 1, day: 2 },
        endDate: { year: 2024, month: 4, day: 2 },
        episodes: 12,
        genres: ["Adventure", "Fantasy"],
        studios: { nodes: [{ name: "Studio One" }] },
        popularity: 120_000,
        favourites: 5_000,
        source: "MANGA",
        staff: {
          edges: [{
            role: "Director",
            node: {
              id: 22,
              name: { full: "Example Director" },
              siteUrl: "https://anilist.co/staff/22",
              image: { large: "https://s4.anilist.co/file/anilistcdn/staff/large/22.jpg" },
            },
          }],
        },
        characters: {
          edges: [{
            role: "MAIN",
            node: {
              id: 33,
              name: { full: "Example Hero" },
              image: { large: "https://s4.anilist.co/file/anilistcdn/character/large/33.jpg" },
              isAdult: false,
            },
          }],
        },
        tags: [{ name: "Found Family", rank: 90, isMediaSpoiler: false, isAdult: false }],
        stats: {
          statusDistribution: [{ status: "CURRENT", amount: 10 }],
          scoreDistribution: [{ score: 85, amount: 15 }],
        },
        recommendations: {
          edges: [{
            node: {
              mediaRecommendation: {
                id: 222,
                title: { romaji: "Related Anime" },
                siteUrl: "https://anilist.co/anime/222",
                coverImage: { large: "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/222.jpg" },
                isAdult: false,
              },
            },
          }],
        },
        relations: {
          edges: [{
            relationType: "SOURCE",
            node: { id: 456, type: "MANGA", isAdult: false, siteUrl: "https://anilist.co/manga/456", title: { romaji: "Source Manga" } },
          }],
        },
        trailer: { id: "abc12345", site: "youtube" },
      },
    },
  };
  const client = new AniListClient("https://graphql.anilist.co", 1_000, async (_input, init) => {
    const request = JSON.parse(String(init?.body)) as { query: string; variables: Record<string, unknown> };
    assert.match(request.query, /MediaDetails/);
    assert.deepEqual(request.variables, { id: 123, type: "ANIME" });
    return new Response(JSON.stringify(payload), { status: 200, headers: { "content-type": "application/json" } });
  });
  const media = await client.getMediaById(123, "ANIME");
  assert.ok(media);
  assert.equal(media.title.romaji, "Example Anime");
  assert.equal(media.staffCredits[0]?.name, "Example Director");
  assert.equal(media.staffCredits[0]?.role, "Director");
  assert.equal(media.characters[0]?.name, "Example Hero");
  assert.equal(media.tags[0]?.isSpoiler, false);
  assert.equal(media.stats.scoreDistribution[0]?.score, 85);
  assert.equal(media.recommendations[0]?.title, "Related Anime");
  assert.equal(media.relations[0]?.category, "manga");
  assert.equal(media.trailer?.url, "https://youtu.be/abc12345");

  const embed = buildMediaEmbed(media).toJSON();
  assert.equal(embed.title?.includes("Example Anime"), true);
  assert.equal(embed.url, "https://anilist.co/anime/123/example");
  assert.ok(embed.fields?.some(field => field.name === "Studio" && field.value.includes("Studio One")));
  assert.ok(embed.fields?.some(field => field.name === "Main Characters" && field.value.includes("Example Hero")));
  assert.ok(buildRelationsEmbeds(media).length > 0);
  assert.ok(buildStatsEmbed(media).data.fields?.length);
  assert.ok(buildTagsEmbed(media).data.description?.includes("Found Family"));
  assert.ok(buildTrendingEmbed([media], "Trending", "Popular this week").data.fields?.length);
});

test("AniList detail parser rejects adult media and invalid IDs", async () => {
  const client = new AniListClient("https://graphql.anilist.co", 1_000, async () =>
    new Response(JSON.stringify({ data: { Media: { id: 1, type: "ANIME", isAdult: true } } }), { status: 200 }),
  );
  assert.equal(await client.getMediaById(1, "ANIME"), null);
  await assert.rejects(() => client.getMediaById(0, "ANIME"), /positive integer/);
});

test("shared embed builders produce consistent titled status and profile embeds", () => {
  assert.ok(buildErrorEmbed("Failure", "Try again").data.title?.startsWith("❌"));
  assert.ok(buildSuccessEmbed("Saved", "Done").data.title?.startsWith("✅"));
  assert.ok(buildInfoEmbed("Details", "Info").data.title?.startsWith("ℹ️"));
  const user = {
    id: 7,
    name: "ExampleUser",
    url: "https://anilist.co/user/ExampleUser",
    avatar: "https://s4.anilist.co/file/anilistcdn/user/avatar/large/7.jpg",
    banner: null,
    about: "A public AniList profile",
    anime: { count: 20, meanScore: 83, episodesWatched: 240, minutesWatched: 3_000, chaptersRead: null, volumesRead: null, genres: [], statuses: [], formats: [] },
    manga: { count: 10, meanScore: 78, episodesWatched: null, minutesWatched: null, chaptersRead: 400, volumesRead: 40, genres: [], statuses: [], formats: [] },
    favorites: {
      anime: [{ id: 1, title: "Example Anime", url: "https://anilist.co/anime/1", image: null }],
      manga: [],
      characters: [],
      staff: [],
      studios: [],
    },
  };
  assert.equal(buildUserProfileEmbed(user).data.url, user.url);
  assert.equal(buildUserFavoritesEmbed(user).data.fields?.length, 5);
});
