import { Button } from "../../UI";
import { Icon } from "../../Icons";

export function CommandSettings({ guildId, busy, onReset, onPublish }: {
  guildId: string;
  busy: boolean;
  onReset: () => void;
  onPublish: () => void;
}) {
  return (
    <>
      <Button onClick={onReset} disabled={busy || !guildId}>Server defaults</Button>
      <Button tone="primary" onClick={onPublish} disabled={busy || !guildId}>Publish commands <Icon name="arrow-up-right" size={13} /></Button>
    </>
  );
}
