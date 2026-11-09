import test from "node:test";
import assert from "node:assert/strict";
import {
  filterMediaNightCandidates,
  sampleMediaNightCandidates,
} from "../helpers/community/community-rankings.js";
import type { AniListMediaNightCandidate } from "../helpers/providers/anilist.js";

const candidates: AniListMediaNightCandidate[] = [
  {
    id: 1, type: "ANIME", title: "Quiet Days", url: "https://anilist.co/anime/1",
    image: null, overview: null, genres: ["Slice of Life"], tags: ["Healing"],
    year: 2024, duration: 24,
  },
  {
    id: 2, type: "ANIME", title: "Mystery Case", url: "https://anilist.co/anime/2",
    image: null, overview: null, genres: ["Mystery"], tags: ["Detective"],
    year: 2023, duration: 24,
  },
  {
    id: 3, type: "MANGA", title: "Explicit Entry", url: "https://anilist.co/manga/3",
    image: null, overview: null, genres: ["Comedy"], tags: ["Ecchi"],
    year: 2022, duration: null,
  },
  {
    id: 4, type: "ANIME", title: "Family Story", url: "https://anilist.co/anime/4",
    image: null, overview: null, genres: ["Drama"], tags: ["Family"],
    year: 2021, duration: 24,
  },
];

test("Media Night excludes provider-tagged adult and sensitive entries", () => {
  const result = filterMediaNightCandidates(candidates, "all");
  assert.deepEqual(result.map((item) => item.id), [1, 2, 4]);
});

test("Media Night mood filters match provider genres and tags", () => {
  assert.deepEqual(filterMediaNightCandidates(candidates, "cozy").map((item) => item.id), [1]);
  assert.deepEqual(filterMediaNightCandidates(candidates, "mystery").map((item) => item.id), [2]);
  assert.deepEqual(filterMediaNightCandidates(candidates, "drama").map((item) => item.id), [4]);
});

test("Media Night sampling returns unique provider candidates within the requested bound", () => {
  const result = sampleMediaNightCandidates(candidates, 3);
  assert.equal(result.length, 3);
  assert.equal(new Set(result.map((item) => item.id)).size, 3);
  assert.ok(result.every((item) => candidates.some((candidate) => candidate.id === item.id)));
  assert.deepEqual(sampleMediaNightCandidates(candidates, 0), []);
  assert.equal(sampleMediaNightCandidates(candidates, 99).length, candidates.length);
});
