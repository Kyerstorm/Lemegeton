import { Icon } from "../../Icons";
import type { Command } from "../../../Types/dashboard";

export function CommandDetails({ command, guideUrl, onCopy, onOpenAccess, disabled }: {
  command: Command;
  guideUrl: (command: Command) => string;
  onCopy: (command: Command) => void;
  onOpenAccess: (command: Command) => void;
  disabled: boolean;
}) {
  const href = guideUrl(command);
  return (
    <div className="command-main">
      <a className="command-name command-name-link" href={href} target="_blank" rel="noreferrer" aria-label={"Open usage guide for /" + (command.fullname || command.name)} title="Open the relevant command guide">
        <span className="command-prefix">/</span>{command.fullname || command.name}<span className="command-link-glyph"><Icon name="arrow-up-right" size={12} /></span>
      </a>
      <p className="command-description">{command.description || "No description provided."}</p>
      <div className="command-tags">
        <span className="tag">{command.section || "Other"}</span>
        <span className="tag">{command.type || "slash"}</span>
        <span className="tag">{command.scope || "guild"}</span>
        {command.protected ? <span className="tag tag-protected">Protected</span> : null}
        {command.required_permissions ? <span className="tag">Discord permission gate</span> : null}
      </div>
      <div className="command-actions">
        <button className="command-copy" type="button" onClick={() => onCopy(command)} title={"Copy /" + (command.fullname || command.name)} aria-label={"Copy invocation for /" + (command.fullname || command.name)}><Icon name="copy" size={13} /><span>Copy command</span></button>
        <a className="command-guide" href={href} target="_blank" rel="noreferrer">Usage guide <Icon name="arrow-up-right" size={12} /></a>
        <button className="command-access-open" type="button" onClick={() => onOpenAccess(command)} disabled={disabled || Boolean(command.protected)} aria-label={"Configure access for /" + command.fullname}><Icon name="shield-check" size={14} /> Access rules</button>
      </div>
    </div>
  );
}
