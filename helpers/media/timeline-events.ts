import type { WikidataRelation } from "../integration/wikidata.js";

export type TimelineDatePrecision = "day" | "month" | "year" | "unknown";

export interface TimelineDate {
  value: string | null;
  precision: TimelineDatePrecision;
  label: string;
}

export interface TimelineEvent {
  id: string;
  title: string;
  description: string | null;
  date: TimelineDate;
  eventType: string;
  sequenceType: "in-universe" | "publication" | "release" | "adaptation" | "continuity";
  sourceName: string;
  sourceUrl: string;
  region?: string | null;
  platform?: string | null;
  continuity?: string | null;
}

function validDateParts(year: number, month?: number, day?: number): boolean {
  if (!Number.isInteger(year) || year < 1 || year > 9999) return false;
  if (month === undefined) return true;
  if (!Number.isInteger(month) || month < 1 || month > 12) return false;
  if (day === undefined) return true;
  if (!Number.isInteger(day) || day < 1) return false;
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
}

/** Preserve the precision supplied by the source; never fill missing month/day values. */
export function normalizeTimelineDate(value: unknown): TimelineDate {
  if (typeof value !== "string") {
    return { value: null, precision: "unknown", label: "Date not supplied" };
  }
  const normalized = value.trim();
  let match = /^(\d{4})$/.exec(normalized);
  if (match) {
    const year = Number(match[1]);
    return validDateParts(year)
      ? { value: normalized, precision: "year", label: normalized }
      : { value: null, precision: "unknown", label: "Date not supplied" };
  }
  match = /^(\d{4})-(\d{2})$/.exec(normalized);
  if (match) {
    const year = Number(match[1]);
    const month = Number(match[2]);
    return validDateParts(year, month)
      ? { value: normalized, precision: "month", label: normalized }
      : { value: null, precision: "unknown", label: "Date not supplied" };
  }
  match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(normalized);
  if (match) {
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    return validDateParts(year, month, day)
      ? { value: normalized, precision: "day", label: normalized }
      : { value: null, precision: "unknown", label: "Date not supplied" };
  }
  return { value: null, precision: "unknown", label: "Date not supplied" };
}

export function timelineDateFromParts(parts: {
  year: number | null;
  month?: number | null;
  day?: number | null;
} | null): TimelineDate {
  if (!parts?.year) return normalizeTimelineDate(null);
  const year = parts.year;
  if (parts.month == null) return normalizeTimelineDate(String(year));
  const month = String(parts.month).padStart(2, "0");
  if (parts.day == null) return normalizeTimelineDate(String(year) + "-" + month);
  return normalizeTimelineDate(String(year) + "-" + month + "-" + String(parts.day).padStart(2, "0"));
}

/** Convert Wikidata's typed series edges into relative work-order records; no calendar date is inferred. */
export function wikidataSequenceEvents(relations: readonly WikidataRelation[]): TimelineEvent[] {
  return relations.flatMap(relation => {
    if (relation.kind !== "sequence"
      || !/^Q[1-9]\d{0,11}$/.test(relation.subjectId)
      || !/^Q[1-9]\d{0,11}$/.test(relation.objectId)
      || !/^P[1-9]\d{0,8}$/.test(relation.propertyId)) return [];
    const relationLabel: Record<string, string> = {
      P155: "follows",
      P156: "is followed by",
      P179: "belongs to the series",
    };
    const label = relationLabel[relation.propertyId] ?? "is related to";
    const subject = relation.subjectLabel ?? relation.subjectId;
    const target = relation.objectLabel ?? relation.objectId;
    return [{
      id: "wikidata:" + relation.subjectId + ":" + relation.propertyId + ":" + relation.objectId,
      title: subject + " " + label + " " + target,
      description: "Relative series/work-order relationship from Wikidata; this record does not establish a date inside the fictional world.",
      date: normalizeTimelineDate(null),
      eventType: "Relative series order (" + relation.propertyId + ")",
      sequenceType: "continuity" as const,
      sourceName: "Wikidata",
      sourceUrl: "https://www.wikidata.org/wiki/" + relation.subjectId,
      continuity: "Wikidata series relationship",
    }];
  }).slice(0, 40);
}

export function sortTimelineEvents<T extends Pick<TimelineEvent, "date" | "title">>(events: readonly T[]): T[] {
  return [...events].sort((left, right) => {
    const leftDate = left.date.value ?? "9999";
    const rightDate = right.date.value ?? "9999";
    return leftDate.localeCompare(rightDate) || left.title.localeCompare(right.title);
  });
}
