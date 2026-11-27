import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { UnsavedChangesDialog } from "../../src/Components/Forms/UnsavedChangesDialog";

describe("UnsavedChangesDialog", () => {
  it("explains the pending changes and routes both user choices", () => {
    const onKeepEditing = vi.fn();
    const onDiscard = vi.fn();
    const props = {
      open: true,
      description: "Your command access changes have not been saved.",
      destructive: false,
      onKeepEditing,
      onDiscard,
    };

    const { rerender } = render(<UnsavedChangesDialog {...props} />);
    expect(screen.getByRole("dialog", { name: "Unsaved changes" })).toBeTruthy();
    expect(screen.getByText(props.description)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Keep editing" }));
    fireEvent.click(screen.getByRole("button", { name: "Discard changes" }));
    expect(onKeepEditing).toHaveBeenCalledTimes(1);
    expect(onDiscard).toHaveBeenCalledTimes(1);

    rerender(<UnsavedChangesDialog {...props} open={false} />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("provides a safe default description and supports a custom action label", () => {
    render(
      <UnsavedChangesDialog
        open
        destructive={false}
        confirmLabel="Leave page"
        onKeepEditing={vi.fn()}
        onDiscard={vi.fn()}
      />,
    );

    expect(screen.getByText("Your changes have not been saved. Discard them and continue?")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Leave page" })).toBeTruthy();
  });
});

describe("dialog keyboard behaviour", () => {
  it("traps focus, closes with Escape, and restores the opener", () => {
    function DialogHarness() {
      const [open, setOpen] = useState(false);

      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>Open dialog</button>
          <UnsavedChangesDialog
            open={open}
            destructive={false}
            onKeepEditing={() => setOpen(false)}
            onDiscard={() => setOpen(false)}
          />
        </>
      );
    }

    render(<DialogHarness />);
    const trigger = screen.getByRole("button", { name: "Open dialog" });
    fireEvent.click(trigger);

    const dialog = screen.getByRole("dialog", { name: "Unsaved changes" });
    const cancel = screen.getByRole("button", { name: "Keep editing" });
    const confirm = screen.getByRole("button", { name: "Discard changes" });
    expect(document.activeElement).toBe(cancel);

    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(confirm);
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(cancel);

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
    expect(document.body.style.overflow).toBe("");
  });
});
