import test from "node:test";
import assert from "node:assert/strict";
import {
  buildGitHubActivityEmbed,
  summarizeGitHubActivity,
  type GitHubCommit,
  type GitHubCommitStats,
} from "../helpers/runtime/github-tracker.js";

function commit(sha: string, committedAt: string): GitHubCommit {
  return {
    sha,
    url: "https://github.com/example/project/commit/" + sha,
    message: "Update " + sha.slice(0, 7),
    author: "contributor",
    committedAt,
  };
}

test("combines additions, deletions and distinct file paths across a commit window", () => {
  const first = commit("a".repeat(40), "2026-11-26T10:00:00.000Z");
  const second = commit("b".repeat(40), "2026-11-26T10:10:00.000Z");
  const commits = [first, second];
  const stats: GitHubCommitStats[] = [
    { sha: first.sha, additions: 15, deletions: 4, files: ["src/a.ts", "src/shared.ts"] },
    { sha: second.sha, additions: 7, deletions: 8, files: ["src/shared.ts", "tests/a.test.ts"] },
  ];

  const summary = summarizeGitHubActivity(commits, stats);
  assert.equal(summary.commits.length, 2);
  assert.equal(summary.additions, 22);
  assert.equal(summary.deletions, 12);
  assert.equal(summary.filesChanged, 3);
  assert.equal(summary.statsFor, 2);
  assert.equal(summary.windowLabel, "10 min window");
});

test("reports partial statistics coverage instead of presenting incomplete totals as complete", () => {
  const commits = [
    commit("a".repeat(40), "2026-11-26T10:00:00.000Z"),
    commit("b".repeat(40), "2026-11-26T10:01:00.000Z"),
    commit("c".repeat(40), "2026-11-26T10:02:00.000Z"),
  ];
  const summary = summarizeGitHubActivity(commits, [
    { sha: "a".repeat(40), additions: 5, deletions: 2, files: ["src/one.ts"] },
  ]);

  assert.equal(summary.additions, 5);
  assert.equal(summary.deletions, 2);
  assert.equal(summary.filesChanged, 1);
  assert.equal(summary.statsFor, 1);
  const embed = buildGitHubActivityEmbed(summary, "example/project", "main").toJSON();
  assert.equal(embed.fields?.[0]?.value, "+5 · 1/3");
  assert.equal(embed.fields?.[1]?.value, "−2 · 1/3");
  assert.equal(embed.fields?.[2]?.value, "1 observed");
});

test("renders compact commit activity with one combined summary", () => {
  const first = commit("a".repeat(40), "2026-11-26T10:00:00.000Z");
  const second = commit("b".repeat(40), "2026-11-26T10:10:00.000Z");
  const commits = [first, second];
  const summary = summarizeGitHubActivity(commits, [
    { sha: first.sha, additions: 15, deletions: 4, files: ["src/a.ts"] },
    { sha: second.sha, additions: 7, deletions: 8, files: ["src/b.ts"] },
  ]);
  const embed = buildGitHubActivityEmbed(summary, "example/project", "main").toJSON();

  assert.equal(embed.title, "GitHub activity");
  assert.match(embed.description ?? "", /2 commits · 10 min window/);
  assert.equal(embed.fields?.[0]?.value, "+22");
  assert.equal(embed.fields?.[1]?.value, "−12");
  assert.equal(embed.fields?.[2]?.value, "2");
  assert.match(embed.footer?.text ?? "", /statistics 2\/2/);
});
