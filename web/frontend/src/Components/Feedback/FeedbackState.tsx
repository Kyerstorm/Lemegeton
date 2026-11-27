import type { ReactNode } from "react";
import { Button } from "../UI/Button";
import { Icon, type IconName } from "../Icons";

export function FeedbackState({ title, message, icon = "alert-circle", actionLabel, onAction, reportHref, children }: {
  title: string;
  message: string;
  icon?: IconName;
  actionLabel?: string;
  onAction?: () => void;
  reportHref?: string;
  children?: ReactNode;
}) {
  return (
    <section className="feedback-state" role="alert">
      <span className="feedback-state-icon" aria-hidden="true"><Icon name={icon} size={17} /></span>
      <div className="feedback-state-copy">
        <strong>{title}</strong>
        <p>{message}</p>
        {children}
      </div>
      {reportHref || (actionLabel && onAction) ? (
        <div className="feedback-state-actions">
          {reportHref ? <a className="button quiet feedback-state-report" href={reportHref} target="_blank" rel="noopener noreferrer">Open GitHub issue tracker</a> : null}
          {actionLabel && onAction ? <Button type="button" tone="quiet" onClick={onAction}>{actionLabel}<Icon name="retry" size={13} /></Button> : null}
        </div>
      ) : null}
    </section>
  );
}
