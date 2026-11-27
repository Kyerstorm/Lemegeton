import test from "node:test";
import assert from "node:assert/strict";
import { chooseBalancedTeam } from "../helpers/runtime/games.js";

test("a new player is assigned to the smaller team", () => {
  const team = chooseBalancedTeam([{ id: "a", member_count: 3, team_number: 1 }, { id: "b", member_count: 1, team_number: 2 }]);
  assert.equal(team?.id, "b");
});

test("team assignment resolves equal rosters deterministically", () => {
  const team = chooseBalancedTeam([{ id: "b", member_count: 2, team_number: 2 }, { id: "a", member_count: 2, team_number: 1 }]);
  assert.equal(team?.id, "a");
});

test("team assignment returns null without configured teams", () => {
  assert.equal(chooseBalancedTeam([]), null);
});
