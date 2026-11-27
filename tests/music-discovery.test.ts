import test from "node:test";
import assert from "node:assert/strict";
import {
  parseLastFmChart,
  parseMusicBrainzArtists,
  parseMusicBrainzLabels,
  MusicDiscovery,
  parseMusicBrainzReleaseGroups,
  parseSetlistFmSetlists,
} from "../helpers/integration/music-discovery.js";

test("MusicBrainz artist search normalizes identity and origin metadata", () => {
  const artists = parseMusicBrainzArtists({
    artists: [{
      id: "12345678-1234-1234-1234-123456789012",
      name: "Artist",
      type: "Group",
      country: "IE",
      "begin-area": { name: "Dublin" },
      "life-span": { begin: "2012" },
      disambiguation: "Irish band",
      score: "98",
    }],
  });
  assert.deepEqual(artists[0], {
    id: "12345678-1234-1234-1234-123456789012",
    name: "Artist",
    type: "Group",
    country: "IE",
    beginArea: "Dublin",
    beginDate: "2012",
    disambiguation: "Irish band",
    score: 98,
  });
  assert.deepEqual(parseMusicBrainzArtists({ artists: [{ name: "Missing ID" }] }), []);
});

test("MusicBrainz discography groups release editions by release-group identity", () => {
  const groups = parseMusicBrainzReleaseGroups({
    "release-groups": [{
      id: "22345678-1234-1234-1234-123456789012",
      title: "First Album",
      "primary-type": "Album",
      "secondary-types": ["Live"],
      "first-release-date": "2024-04-01",
    }],
  });
  assert.deepEqual(groups[0], {
    id: "22345678-1234-1234-1234-123456789012",
    title: "First Album",
    type: "Album",
    secondaryTypes: ["Live"],
    firstReleaseDate: "2024-04-01",
  });
});

test("Last.fm global charts normalize artist and track entries", () => {
  const artists = parseLastFmChart({
    artists: { artist: [{ name: "Artist", listeners: "100", playcount: "250", url: "https://www.last.fm/music/Artist", mbid: "mbid", "@attr": { rank: "1" } }] },
  }, "artists");
  const tracks = parseLastFmChart({
    tracks: { track: [{ name: "Track", artist: { name: "Artist", mbid: "artist-mbid" }, listeners: "25", playcount: "80", url: "https://www.last.fm/music/Artist/_/Track" }] },
  }, "tracks");
  assert.equal(artists[0]?.title, "Artist");
  assert.equal(artists[0]?.rank, 1);
  assert.equal(artists[0]?.playcount, 250);
  assert.equal(tracks[0]?.title, "Track");
  assert.equal(tracks[0]?.artist, "Artist");
  assert.equal(tracks[0]?.mbid, "artist-mbid");
});

test("setlist.fm results retain venue, location, date, tour and song order", () => {
  const setlists = parseSetlistFmSetlists({
    setlist: [{
      id: "setlist-id",
      artist: { name: "Artist" },
      venue: { name: "Venue", city: { name: "Dublin", country: { name: "Ireland" } } },
      eventDate: "12-06-2026",
      tour: { name: "Summer Tour" },
      url: "https://www.setlist.fm/setlist/example",
      set: [{ song: [{ name: "First" }, { name: "Second" }] }],
    }],
  });
  assert.deepEqual(setlists[0], {
    id: "setlist-id",
    artist: "Artist",
    venue: "Venue",
    city: "Dublin",
    country: "Ireland",
    date: "12-06-2026",
    tour: "Summer Tour",
    songs: ["First", "Second"],
    url: "https://www.setlist.fm/setlist/example",
  });
});

test("MusicBrainz labels preserve identity and label-specific metadata", () => {
  const labels = parseMusicBrainzLabels({ labels: [{
    id: "32345678-1234-1234-1234-123456789012",
    name: "Example Records",
    type: "Original Production",
    country: "GB",
    "begin-area": { name: "London" },
    "life-span": { begin: "1998", end: null },
    "label-code": "LC 12345",
    disambiguation: "Independent record label",
    score: "97",
  }] });
  assert.deepEqual(labels[0], {
    id: "32345678-1234-1234-1234-123456789012",
    name: "Example Records",
    type: "Original Production",
    country: "GB",
    beginArea: "London",
    beginDate: "1998",
    endDate: null,
    labelCode: "LC 12345",
    disambiguation: "Independent record label",
    score: 97,
    sourceUrl: "https://musicbrainz.org/label/32345678-1234-1234-1234-123456789012",
  });
  assert.deepEqual(parseMusicBrainzLabels({ labels: [{ id: "bad", name: "Invalid" }] }), []);
});

test("MusicBrainz label search uses the official label resource and a bounded query", async () => {
  let requested = new URL("https://example.com");
  const fetcher: typeof fetch = async input => {
    requested = new URL(String(input));
    return new Response(JSON.stringify({ labels: [{
      id: "32345678-1234-1234-1234-123456789012",
      name: "Example Records",
      "label-code": "LC 12345",
    }] }), { status: 200, headers: { "content-type": "application/json" } });
  };
  const client = new MusicDiscovery({ lastFmApiKey: "", setlistFmApiKey: "" } as never, fetcher, 0);
  const labels = await client.searchLabels("Example Records");
  assert.equal(labels[0]?.name, "Example Records");
  assert.equal(requested.hostname, "musicbrainz.org");
  assert.equal(requested.pathname, "/ws/2/label");
  assert.equal(requested.searchParams.get("fmt"), "json");
  assert.equal(requested.searchParams.get("limit"), "10");
  assert.match(requested.searchParams.get("query") ?? "", /^label:/);
  assert.deepEqual(await client.label("invalid-id"), null);
});
