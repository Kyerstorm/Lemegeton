import { Card } from "../../UI";
import type { OverviewGuild, OverviewUser } from "./types";

export function ServerSummary({ currentGuild, guildId, user }: { currentGuild?: OverviewGuild; guildId: string; user: OverviewUser }) {
  return (
    <Card eyebrow="SELECTED SERVER" title="Guild context" index="G / 01">
      <dl className="definition-list">
        <div><dt>Server</dt><dd>{currentGuild?.name || "—"}</dd></div>
        <div><dt>Guild ID</dt><dd className="mono">{guildId || "—"}</dd></div>
        <div><dt>Your permission</dt><dd>{currentGuild?.administrator ? "Administrator" : user ? "Manage Server" : "Unknown"}</dd></div>
        <div><dt>Bot membership</dt><dd>{currentGuild ? "Connected" : "Unavailable"}</dd></div>
      </dl>
    </Card>
  );
}
