import { useState } from "react";
import type { ReactNode } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useDialogFocus } from "../../src/Components/Hooks/useDialogFocus";

function TestDialog({ open, label, onEscape, children }: {
  open: boolean;
  label: string;
  onEscape?: () => void;
  children: ReactNode;
}) {
  const ref = useDialogFocus(open, undefined, onEscape);
  if (!open) return null;

  return (
    <section ref={ref} role="dialog" aria-modal="true" aria-label={label} tabIndex={-1}>
      {children}
    </section>
  );
}

function NestedDialogHarness({ onOuterActionFocus }: { onOuterActionFocus: () => void }) {
  const [outerOpen, setOuterOpen] = useState(true);
  const [innerOpen, setInnerOpen] = useState(false);

  return (
    <>
      <button type="button" onClick={() => setOuterOpen(true)}>Open outer dialog</button>
      <TestDialog open={outerOpen} label="Outer dialog" onEscape={() => setOuterOpen(false)}>
        <button type="button" onClick={() => setInnerOpen(true)}>Open nested dialog</button>
        <button type="button" onFocus={onOuterActionFocus}>Outer action</button>
      </TestDialog>
      <TestDialog open={innerOpen} label="Nested dialog" onEscape={() => setInnerOpen(false)}>
        <button type="button">Nested first action</button>
        <button type="button">Nested last action</button>
      </TestDialog>
    </>
  );
}

describe("useDialogFocus", () => {
  it("keeps keyboard focus in the topmost nested dialog and restores focus in order", () => {
    const onOuterActionFocus = vi.fn();
    render(<NestedDialogHarness onOuterActionFocus={onOuterActionFocus} />);

    const nestedTrigger = screen.getByRole("button", { name: "Open nested dialog" });
    fireEvent.click(nestedTrigger);

    const nestedFirst = screen.getByRole("button", { name: "Nested first action" });
    const nestedLast = screen.getByRole("button", { name: "Nested last action" });
    expect(document.activeElement).toBe(nestedFirst);

    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(nestedLast);
    expect(onOuterActionFocus).not.toHaveBeenCalled();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Nested dialog" })).toBeNull();
    expect(document.activeElement).toBe(nestedTrigger);
    expect(document.body.style.overflow).toBe("hidden");

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Outer dialog" })).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Open outer dialog" }));
    expect(document.body.style.overflow).toBe("");
  });
  it("consumes Escape when the topmost dialog cannot be dismissed", () => {
    const dismissOuter = vi.fn();
    const { unmount } = render(
      <>
        <TestDialog open label="Outer dialog" onEscape={dismissOuter}>
          <button type="button">Outer action</button>
        </TestDialog>
        <TestDialog open label="Busy dialog">
          <button type="button">Busy action</button>
        </TestDialog>
      </>,
    );

    const event = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    document.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
    expect(dismissOuter).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "Busy dialog" })).toBeTruthy();
    unmount();
  });

});