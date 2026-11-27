import test from "node:test";
import assert from "node:assert/strict";
import {
  normalizeTimelineDate,
  sortTimelineEvents,
  timelineDateFromParts,
} from "../helpers/media/timeline-events.js";

test("timeline dates preserve day, month and year precision", () => {
  assert.deepEqual(normalizeTimelineDate("2024-06-03"), {
    value: "2024-06-03", precision: "day", label: "2024-06-03",
  });
  assert.equal(normalizeTimelineDate("2024-06").precision, "month");
  assert.equal(normalizeTimelineDate("2024").precision, "year");
  assert.equal(timelineDateFromParts({ year: 2020, month: 3, day: null }).value, "2020-03");
  assert.equal(timelineDateFromParts({ year: 2020, month: null, day: null }).value, "2020");
});

test("timeline dates reject invalid or guessed values", () => {
  assert.equal(normalizeTimelineDate("2024-02-30").precision, "unknown");
  assert.equal(normalizeTimelineDate("2024-13").precision, "unknown");
  assert.equal(normalizeTimelineDate("circa 2000").value, null);
  assert.equal(timelineDateFromParts(null).value, null);
});

test("Wikidata series edges preserve relative order without inventing in-universe dates", () => {
  const events = wikidataSequenceEvents([
    {
      subjectId: "Q100",
      objectId: "Q200",
      subjectLabel: "Part Two",
      objectLabel: "Part One",
      propertyId: "P155",
      kind: "sequence",
    },
    {
      subjectId: "Q100",
      objectId: "Q300",
      subjectLabel: "Part Two",
      objectLabel: "Series",
      propertyId: "P179",
      kind: "sequence",
    },
    {
      subjectId: "Q100",
      objectId: "Q999",
      subjectLabel: "Ignored",
      objectLabel: "Organization",
      propertyId: "P749",
      kind: "organization",
    },
  ]);
  assert.equal(events.length, 2);
  assert.match(events[0]!.title, /Part Two follows Part One/);
  assert.equal(events[0]!.date.precision, "unknown");
  assert.equal(events[0]!.date.value, null);
  assert.equal(events[0]!.sequenceType, "continuity");
  assert.match(events[0]!.description ?? "", /does not establish a date inside the fictional world/);
  assert.equal(events[0]!.sourceUrl, "https://www.wikidata.org/wiki/Q100");
});

test("timeline event ordering retains undated events at the end", () => {
  const events = [
    { title: "Unknown", date: normalizeTimelineDate(null) },
    { title: "Later", date: normalizeTimelineDate("2024") },
    { title: "Earlier", date: normalizeTimelineDate("2001-02") },
  ];
  assert.deepEqual(sortTimelineEvents(events).map(event => event.title), ["Earlier", "Later", "Unknown"]);
});
