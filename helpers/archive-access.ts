export const GLOBAL_MODERATOR_IDS = new Set(
  (process.env.ARCHIVE_GLOBAL_MODERATOR_IDS ?? "")
    .split(",")
    .map((id) => id.trim())
    .filter((id) => /^\d{17,20}$/.test(id)),
);

export function isGlobalArchiveModerator(userId: string): boolean {
  return GLOBAL_MODERATOR_IDS.has(userId);
}
