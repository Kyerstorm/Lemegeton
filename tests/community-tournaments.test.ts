import test from "node:test";
import assert from "node:assert/strict";
import {
  normalizeTournamentCandidates,
  parseTournamentCandidates,
  resolveTournamentMatch,
  tournamentMatchups,
  normalizeSeasonItemType,
  validateSeasonWindow,
} from "../helpers/community/community-tournaments.js";

test("single-elimination tournaments require 4, 8 or 16 distinct HTTPS-backed candidates", () => {
  assert.throws(() => normalizeTournamentCandidates([{title:"A",sourceUrl:"https://example.com/a"},{title:"B",sourceUrl:"https://example.com/b"}]), /4, 8 or 16/);
  assert.throws(() => normalizeTournamentCandidates(Array.from({length:4},(_,i)=>({title:i===3?"A":String.fromCharCode(65+i),sourceUrl:"https://example.com/"+i}))), /distinct title/);
  assert.throws(() => normalizeTournamentCandidates(Array.from({length:4},(_,i)=>({title:"Title "+i,sourceUrl:"http://example.com/"+i}))), /HTTPS/i);
  assert.equal(normalizeTournamentCandidates(Array.from({length:8},(_,i)=>({title:"Title "+i,sourceUrl:"https://example.com/"+i}))).length,8);
});

test("tournament candidates parse one title and HTTPS source per line", () => {
  assert.deepEqual(parseTournamentCandidates("A | https://example.com/a\nB | https://example.com/b\nC | https://example.com/c\nD | https://example.com/d").map(item=>item.title),["A","B","C","D"]);
  assert.throws(()=>parseTournamentCandidates("A\nB"),/one candidate per line/);
});

test("tournament bracket seeds are paired in fixed order", () => {
  assert.deepEqual(tournamentMatchups([1,2,3,4]),[[1,2],[3,4]]);
  assert.deepEqual(tournamentMatchups([1,2,3,4,5,6,7,8]),[[1,2],[3,4],[5,6],[7,8]]);
  assert.deepEqual(tournamentMatchups([2,3]),[[2,3]]);
});

test("tournament ties use the lower seed, including matches with no votes", () => {
  assert.deepEqual(resolveTournamentMatch(3,2,1,2),{winner:"a",decision:"votes"});
  assert.deepEqual(resolveTournamentMatch(0,0,2,1),{winner:"b",decision:"seed_tiebreak"});
  assert.deepEqual(resolveTournamentMatch(4,4,3,4),{winner:"a",decision:"seed_tiebreak"});
});

test("Community Season items are restricted to existing supported activity types", () => {
  for(const value of ["daily_drop","ranking","session","tournament","spotlight","collection","trail"])assert.equal(normalizeSeasonItemType(value),value);
  assert.throws(()=>normalizeSeasonItemType("reminder"),/supported season item/);
});

test("Community Season dates are valid and bounded to 180 days", () => {
  const now=new Date("2026-11-13T12:00:00.000Z");
  assert.doesNotThrow(()=>validateSeasonWindow(now,new Date("2027-02-13T12:00:00.000Z"),now));
  assert.throws(()=>validateSeasonWindow(new Date("invalid"),now,now),/valid dates/);
  assert.throws(()=>validateSeasonWindow(new Date("2026-11-12T12:00:00.000Z"),new Date("2026-11-20T12:00:00.000Z"),now),/past/);
  assert.throws(()=>validateSeasonWindow(now,new Date("2027-12-13T12:00:00.000Z"),now),/180 days/);
});