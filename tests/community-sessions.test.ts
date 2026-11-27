import test from "node:test";
import assert from "node:assert/strict";
import { normalizeCommunitySessionNomination } from "../helpers/community/community-sessions.js";

test("session nominations validate activity, future time, media URL and capacity", () => {
  const normalized = normalizeCommunitySessionNomination({
    title: "Friday watch session", description: "A server watch event",
    activity: "watch", scheduledAt: new Date(Date.now() + 60 * 60 * 1000), capacity: 20,
    mediaTitle: "Example Series", mediaUrl: "https://anilist.co/anime/1",
  });
  assert.equal(normalized.title, "Friday watch session");
  assert.equal(normalized.activity, "watch");
  assert.equal(normalized.capacity, 20);
  assert.equal(normalized.mediaUrl, "https://anilist.co/anime/1");
  assert.throws(() => normalizeCommunitySessionNomination({
    title: "Invalid", description: "", activity: "unknown",
    scheduledAt: new Date(Date.now() + 60 * 60 * 1000),
  }), /Choose Watch, Read, Play or Discuss/);
  assert.throws(() => normalizeCommunitySessionNomination({
    title: "Past event", description: "", activity: "watch",
    scheduledAt: new Date(Date.now() - 60_000),
  }), /future date and time/);
  assert.throws(() => normalizeCommunitySessionNomination({
    title: "Bad link", description: "", activity: "watch",
    scheduledAt: new Date(Date.now() + 60 * 60 * 1000), mediaUrl: "http://example.com",
  }), /HTTPS/);
  assert.throws(() => normalizeCommunitySessionNomination({
    title: "Full room", description: "", activity: "watch",
    scheduledAt: new Date(Date.now() + 60 * 60 * 1000), capacity: 1,
  }), /capacity must be between 2 and 200/);
});
