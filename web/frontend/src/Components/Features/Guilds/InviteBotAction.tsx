import { Icon } from "../../Icons";

function safeInviteUrl(value?: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" || !["discord.com", "discordapp.com"].includes(url.hostname)
      || url.pathname !== "/oauth2/authorize" || url.username || url.password) return null;
    return url.toString();
  } catch {
    return null;
  }
}

export function InviteBotAction({ href }: { href?: string | null }) {
  const safeHref = safeInviteUrl(href);
  if (!safeHref) return <span className="server-picker-missing">Invite unavailable</span>;
  return <a className="server-invite-link" href={safeHref} target="_blank" rel="noopener noreferrer">Invite bot <Icon name="arrow-up-right" size={12} /></a>;
}
