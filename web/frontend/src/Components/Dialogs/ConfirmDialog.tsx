import type { ReactNode } from "react";
import { useDialogFocus } from "../Hooks/useDialogFocus";
import { Button } from "../UI/Button";
import { HoldToConfirmButton } from "../UI/HoldToConfirmButton";

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  busy?: boolean;
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open, title, message, confirmLabel, cancelLabel = "Cancel",
  busy = false, destructive = false, onConfirm, onCancel,
}: ConfirmDialogProps) {
  const dialogRef = useDialogFocus(
    open,
    ".dialog-actions button",
    busy ? undefined : onCancel,
  );

  if (!open) return null;
  return (
    <div className="modal-scrim" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget && !busy) onCancel(); }}>
      <section ref={dialogRef} className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-dialog-title" aria-describedby="confirm-dialog-message" aria-busy={busy || undefined} tabIndex={-1}>
        <p className="eyebrow">{destructive ? "DESTRUCTIVE ACTION" : "CONFIRM ACTION"}</p>
        <h2 id="confirm-dialog-title">{title}</h2>
        <div id="confirm-dialog-message" className="confirm-dialog-message">{message}</div>
        <div className="dialog-actions">
          <Button type="button" onClick={onCancel} disabled={busy}>{cancelLabel}</Button>
          {destructive ? (
            <HoldToConfirmButton
              aria-label={"Hold to confirm: " + confirmLabel}
              className="button-destructive"
              disabled={busy}
              duration={1600}
              onConfirm={() => onConfirm()}
            >
              {"Hold to " + confirmLabel.toLocaleLowerCase()}
            </HoldToConfirmButton>
          ) : (
            <Button type="button" tone="primary" onClick={onConfirm} disabled={busy}>{busy ? "Working…" : confirmLabel}</Button>
          )}
        </div>
      </section>
    </div>
  );
}

export type DestructiveActionDialogProps = Omit<ConfirmDialogProps, "destructive">;

export function DestructiveActionDialog(props: DestructiveActionDialogProps) {
  return <ConfirmDialog {...props} destructive />;
}
