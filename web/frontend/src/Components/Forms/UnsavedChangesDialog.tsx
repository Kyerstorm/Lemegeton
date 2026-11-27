import { ConfirmDialog } from "../Dialogs/ConfirmDialog";

export function UnsavedChangesDialog({ open, description, confirmLabel = "Discard changes", destructive = true, onKeepEditing, onDiscard }: {
  open: boolean;
  description?: string;
  confirmLabel?: string;
  destructive?: boolean;
  onKeepEditing: () => void;
  onDiscard: () => void;
}) {
  return (
    <ConfirmDialog
      open={open}
      title="Unsaved changes"
      message={description || "Your changes have not been saved. Discard them and continue?"}
      confirmLabel={confirmLabel}
      cancelLabel="Keep editing"
      destructive={destructive}
      onConfirm={onDiscard}
      onCancel={onKeepEditing}
    />
  );
}
