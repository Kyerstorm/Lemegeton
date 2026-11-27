export const GLOBAL_MODERATOR_IDS = new Set<string>();

export function configureArchiveAccess(moderatorIds: readonly string[]): void {
  GLOBAL_MODERATOR_IDS.clear();
  for (const id of moderatorIds) {
    if (/^\d{17,20}$/.test(id)) GLOBAL_MODERATOR_IDS.add(id);
  }
}

export function isGlobalArchiveModerator(userId: string): boolean {
  return GLOBAL_MODERATOR_IDS.has(userId);
}
