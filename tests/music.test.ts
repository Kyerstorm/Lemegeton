import test from "node:test";
import assert from "node:assert/strict";
import {
  cleanMusicText,
  extractSoundCloudUserId,
  extractSpotifyArtistId,
  extractYoutubeChannelId,
  extractYoutubeHandle,
  musicReleaseKey,
  parseSoundCloudFeed,
} from "../helpers/integration/music.js";

test("Spotify artist IDs resolve from direct IDs and canonical artist URLs only", () => {
  const id = "4Z8W4fKeB5YxbusRsdQVPb";
  assert.equal(extractSpotifyArtistId(id), id);
  assert.equal(extractSpotifyArtistId("https://open.spotify.com/artist/" + id), id);
  assert.equal(extractSpotifyArtistId("https://example.com/artist/" + id), null);
  assert.equal(extractSpotifyArtistId("https://open.spotify.com/track/" + id), null);
});

test("YouTube channel IDs and handles are parsed without accepting other hosts", () => {
  const channelId = "UC1234567890123456789012";
  assert.equal(extractYoutubeChannelId(channelId), channelId);
  assert.equal(extractYoutubeChannelId("https://www.youtube.com/channel/" + channelId), channelId);
  assert.equal(extractYoutubeChannelId("https://youtube.example/channel/" + channelId), null);
  assert.equal(extractYoutubeHandle("https://www.youtube.com/@Artist_Official"), "Artist_Official");
  assert.equal(extractYoutubeHandle("https://example.com/@Artist_Official"), null);
});

test("SoundCloud user IDs are extracted from provider feed identifiers", () => {
  assert.equal(extractSoundCloudUserId("soundcloud:users:123456"), "123456");
  assert.equal(extractSoundCloudUserId("no user id"), null);
});

test("SoundCloud RSS releases decode entities and reject non-SoundCloud links", () => {
  const xml = `<rss><channel>
    <item><title><![CDATA[Track &amp; Mix]]></title><link>https://soundcloud.com/artist/track</link><guid>soundcloud:tracks:1</guid><pubDate>Mon, 02 Jan 2006 15:04:05 GMT</pubDate></item>
    <item><title>Unsafe</title><link>https://example.com/track</link><guid>2</guid></item>
  </channel></rss>`;
  const releases = parseSoundCloudFeed(xml, "Artist");
  assert.equal(releases.length, 1);
  assert.equal(releases[0]?.title, "Track & Mix");
  assert.equal(releases[0]?.artist, "Artist");
  assert.equal(releases[0]?.provider, "soundcloud");
  assert.equal(releases[0]?.url, "https://soundcloud.com/artist/track");
  assert.equal(releases[0]?.release_id, "soundcloud:tracks:1");
  assert.equal(releases[0]?.release_date, "2006-01-02T15:04:05.000Z");
});

test("music notification IDs are namespaced by provider", () => {
  assert.equal(musicReleaseKey({ provider: "spotify", release_id: "123" }), "spotify:123");
  assert.notEqual(
    musicReleaseKey({ provider: "spotify", release_id: "123" }),
    musicReleaseKey({ provider: "youtube", release_id: "123" }),
  );
});

test("music embed text neutralizes mass mentions and escapes markdown", () => {
  const cleaned = cleanMusicText("@everyone *new* @here", 100);
  assert.ok(!cleaned.includes("@everyone"));
  assert.ok(!cleaned.includes("@here"));
  assert.ok(cleaned.includes("\\*new\\*"));
});
