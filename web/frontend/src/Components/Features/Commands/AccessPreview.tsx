import type { CommandAccessPolicy, CommandAccessResponse } from "../../../Types/dashboard";

function selectedNames(ids: string[], options: { id: string; name: string }[]): string[] {
  return ids.map(id => options.find(option => option.id === id)?.name ?? "Unknown item");
}

export function AccessPreview({ policy, options }: {
  policy: CommandAccessPolicy;
  options: CommandAccessResponse;
}) {
  const roles = selectedNames(policy.role_ids, options.roles);
  const channels = selectedNames(policy.channel_ids, options.channels);
  const roleSummary = policy.role_mode === "everyone"
    ? "Everyone"
    : policy.role_mode === "include"
      ? roles.length ? "Only " + roles.join(", ") : "No roles selected — access is denied"
      : roles.length ? "Everyone except " + roles.join(", ") : "Everyone";
  const channelSummary = policy.channel_mode === "all"
    ? "All supported channels"
    : policy.channel_mode === "include"
      ? channels.length ? "Only #" + channels.join(", #") : "No channels selected — access is denied"
      : channels.length ? "All except #" + channels.join(", #") : "All supported channels";

  return (
    <div className="note-block" aria-live="polite">
      <strong>Effective access preview</strong>
      <p>{roleSummary} · {channelSummary}. Both rules must allow the interaction.</p>
    </div>
  );
}
