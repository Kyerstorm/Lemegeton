/** Replace the placeholder ID with the bot's real animated loading emoji. */
export const emoji = {
  loading: "<a:loading:000000000000000000>",
} as const;

export function loadingMessage(activity: string): string {
  return `${emoji.loading} ${activity}`;
}
