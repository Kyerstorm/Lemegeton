export interface MetadataSourceAuditInput {
  provider: string;
  category: string;
  id: string | number;
  url: string;
  fields: Record<string, unknown>;
}

export interface MetadataSourceAudit {
  provider: string;
  category: string;
  id: string;
  url: string;
  presentFields: string[];
  missingFields: string[];
  freshness: "not-reported";
}

const STANDARD_FIELDS = ["description", "releaseDate", "creators", "genres", "image"] as const;

function hasValue(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  if (typeof value === "string") return value.trim().length > 0;
  if (Array.isArray(value)) return value.length > 0;
  return true;
}

export function auditMetadataSource(input: MetadataSourceAuditInput): MetadataSourceAudit {
  const presentFields = STANDARD_FIELDS.filter(field => hasValue(input.fields[field]));
  return {
    provider: input.provider.trim().slice(0, 60),
    category: input.category.trim().slice(0, 40),
    id: String(input.id).slice(0, 100),
    url: input.url,
    presentFields: [...presentFields],
    missingFields: STANDARD_FIELDS.filter(field => !presentFields.includes(field)),
    freshness: "not-reported",
  };
}
