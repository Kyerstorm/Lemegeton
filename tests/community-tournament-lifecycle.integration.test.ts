import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { closeDatabase, initDatabase } from "../src/utility/database/libsql/database.js";
import {
  advanceCommunityTournament,
  cancelCommunityTournament,
  createCommunityTournament,
  getCommunityTournament,
  getCommunityTournamentAudit,
  withdrawCommunityTournamentCandidate,
  voteInCommunityTournament,
} from "../helpers/community/community-tournaments.js";

const guildId = "987654321098765432";
const otherGuildId = "987654321098765433";
const creatorId = "123456789012345671";
const voterId = "123456789012345672";
const managerId = "123456789012345673";
const outsiderId = "123456789012345674";

test("tournament withdrawals create walkovers and retain a guild-scoped bracket audit", async () => {
  const directory = await mkdtemp(join(tmpdir(), "lemegeton-tournament-lifecycle-"));
  const closesAt = new Date(Date.now() + 60_000);
  try {
    await initDatabase({ path: join(directory, "bot.db"), primaryGuildId: guildId });

    const tournamentId = await createCommunityTournament({
      guildId,
      creatorId,
      title: "Withdrawal lifecycle",
      description: "A database-backed bracket lifecycle test.",
      closesAt,
      candidates: [
        { title: "Candidate A", sourceUrl: "https://example.com/a" },
        { title: "Candidate B", sourceUrl: "https://example.com/b" },
        { title: "Candidate C", sourceUrl: "https://example.com/c" },
        { title: "Candidate D", sourceUrl: "https://example.com/d" },
      ],
    });
    assert.deepEqual(await getCommunityTournamentAudit(otherGuildId, tournamentId), []);
    const initial = await getCommunityTournament(guildId, tournamentId);
    assert.ok(initial);
    const firstMatch = initial.matches.find(match => match.match_number === 1)!;
    const secondMatch = initial.matches.find(match => match.match_number === 2)!;

    await assert.rejects(
      withdrawCommunityTournamentCandidate(guildId, tournamentId, firstMatch.candidate_a_id, outsiderId, false),
      /tournament creator or a server manager/i,
    );
    await withdrawCommunityTournamentCandidate(
      guildId, tournamentId, firstMatch.candidate_a_id, creatorId, false, "Source was removed.",
    );

    const afterWithdrawal = await getCommunityTournament(guildId, tournamentId);
    assert.ok(afterWithdrawal);
    const walkover = afterWithdrawal.matches.find(match => match.id === firstMatch.id)!;
    assert.equal(walkover.status, "completed");
    assert.equal(walkover.decision, "withdrawal");
    assert.equal(walkover.winner_candidate_id, firstMatch.candidate_b_id);

    await voteInCommunityTournament(guildId, voterId, secondMatch.id, secondMatch.candidate_b_id);
    await assert.rejects(
      withdrawCommunityTournamentCandidate(guildId, tournamentId, secondMatch.candidate_a_id, creatorId, false),
      /ballot has been cast/i,
    );

    const advanced = await advanceCommunityTournament(
      guildId, tournamentId, creatorId, false, new Date(closesAt.getTime() + 1_000),
    );
    assert.deepEqual(advanced, { status: "open", round: 2, winnerTitle: null });
    const finalRound = await getCommunityTournament(guildId, tournamentId);
    assert.ok(finalRound);
    assert.equal(finalRound.matches.filter(match => match.round_number === 2 && match.status === "open").length, 1);
    const audit = await getCommunityTournamentAudit(guildId, tournamentId, 10);
    assert.ok(audit.some(item => item.action === "created"));
    assert.ok(audit.some(item => item.action === "candidate_withdrawn"
      && item.candidate_id === firstMatch.candidate_a_id
      && item.details === "Source was removed."));
    assert.ok(audit.some(item => item.action === "round_advanced" && item.round_number === 2));

    await assert.rejects(
      cancelCommunityTournament(guildId, tournamentId, outsiderId, false),
      /creator or a server manager/i,
    );
    await cancelCommunityTournament(guildId, tournamentId, managerId, true);
    const finalAudit = await getCommunityTournamentAudit(guildId, tournamentId, 10);
    assert.ok(finalAudit.some(item => item.action === "cancelled" && item.actor_id === managerId));
  } finally {
    await closeDatabase().catch(() => undefined);
    await rm(directory, { recursive: true, force: true });
  }
});
