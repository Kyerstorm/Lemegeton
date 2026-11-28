import type { AuditEntry, Guild, Overview, SystemStatus, User } from "../../../Types/dashboard";

export type OverviewBot = NonNullable<Overview["bot"]>;
export type OverviewGuild = Pick<Guild, "name" | "administrator">;
export type OverviewSystem = SystemStatus;
export type OverviewAuditEntry = AuditEntry;
export type OverviewUser = Pick<User, "id"> | null;
