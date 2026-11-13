export interface ChannelPermissionSnapshot {
  viewChannel: boolean;
  sendMessages: boolean;
  embedLinks: boolean;
}

export function missingChannelPermissions(snapshot: ChannelPermissionSnapshot): string[] {
  const missing: string[] = [];
  if (!snapshot.viewChannel) missing.push("View Channel");
  if (!snapshot.sendMessages) missing.push("Send Messages");
  if (!snapshot.embedLinks) missing.push("Embed Links");
  return missing;
}
