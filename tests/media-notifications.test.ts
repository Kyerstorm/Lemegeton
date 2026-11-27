import test from "node:test";
import assert from "node:assert/strict";
import { mediaFollowSnapshotKey, mediaReleaseEventKey, resolveDueFollowEpisode } from "../helpers/media/media-notifications.js";

const now = new Date("2026-11-15T12:00:00.000Z");

test("follow resolver uses a stored due episode when provider response has moved ahead", () => {
  assert.equal(resolveDueFollowEpisode({
    next_episode: 5,
    next_airing_at: new Date("2026-11-15T11:59:00.000Z"),
    last_notified_episode: 4,
  }, { episode: 6, airingAt: Math.floor(new Date("2026-11-22T12:00:00Z").getTime() / 1000) }, now), 5);
});

test("follow resolver returns provider episode only once its schedule is due", () => {
  assert.equal(resolveDueFollowEpisode({
    next_episode: null, next_airing_at: null, last_notified_episode: 4,
  }, { episode: 5, airingAt: Math.floor(new Date("2026-11-15T12:00:30Z").getTime() / 1000) }, now), 5);
  assert.equal(resolveDueFollowEpisode({
    next_episode: null, next_airing_at: null, last_notified_episode: 4,
  }, { episode: 5, airingAt: Math.floor(new Date("2026-11-15T12:02:00Z").getTime() / 1000) }, now), null);
});

test("follow resolver does not re-notify an acknowledged episode", () => {
  assert.equal(resolveDueFollowEpisode({
    next_episode: 5,
    next_airing_at: new Date("2026-11-15T11:59:00Z"),
    last_notified_episode: 5,
  }, { episode: 5, airingAt: Math.floor(new Date("2026-11-15T11:59:00Z").getTime() / 1000) }, now), null);
});

test("media follow snapshot keys ignore object key order but change with provider metadata", () => {
  assert.equal(mediaFollowSnapshotKey({ status: "RELEASING", chapters: 12 }),
    mediaFollowSnapshotKey({ chapters: 12, status: "RELEASING" }));
  assert.notEqual(mediaFollowSnapshotKey({ status: "RELEASING", chapters: 12 }),
    mediaFollowSnapshotKey({ status: "FINISHED", chapters: 12 }));
});

test("media release event keys are stable and include provider event identity", () => {
  const release = {
    title: "Example episode",
    provider: "AniList",
    url: "https://anilist.co/anime/1",
    when: new Date("2026-11-16T18:00:00.000Z"),
  };
  assert.equal(mediaReleaseEventKey(release), mediaReleaseEventKey({ ...release, when: new Date(release.when) }));
  assert.notEqual(mediaReleaseEventKey(release), mediaReleaseEventKey({ ...release, title: "Example episode 2" }));
});
