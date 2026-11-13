import test from "node:test";
import assert from "node:assert/strict";
import { isSupportedSocialUrl, rewriteSocialUrl } from "../src/integrations/social-embed.js";

test("legacy social embed rewrites supported exact hosts and subdomains", () => {
  assert.equal(rewriteSocialUrl("https://x.com/user/status/1"), "https://xeezz.com/user/status/1");
  assert.equal(rewriteSocialUrl("https://www.reddit.com/r/example"), "https://redditez.com/r/example");
  assert.equal(rewriteSocialUrl("https://vm.tiktok.com/abc123/"), "https://tiktokez.com/abc123/");
  assert.equal(rewriteSocialUrl("https://www.bilibili.com/video/1"), "https://bilibiliez.com/video/1");
  assert.equal(isSupportedSocialUrl("https://imgur.com/a/1"), true);
});

test("social embed rewrites reject lookalike hosts, unsupported protocols and credentials", () => {
  assert.equal(rewriteSocialUrl("https://x.com.evil.example/a"), null);
  assert.equal(rewriteSocialUrl("https://notreddit.com/r/example"), null);
  assert.equal(rewriteSocialUrl("javascript:alert(1)"), null);
  assert.equal(rewriteSocialUrl("https://user:pass@x.com/example"), null);
  assert.equal(isSupportedSocialUrl("https://example.com"), false);
});
