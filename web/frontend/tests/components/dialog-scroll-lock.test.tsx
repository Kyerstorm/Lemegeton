import { useState } from "react";
import type { ReactNode } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useDialogFocus } from "../../src/Components/Hooks/useDialogFocus";

function TestDialog({ open, label, children }: {
  open: boolean;
  label: string;
  children: ReactNode;
}) {
  const ref = useDialogFocus(open);
  if (!open) return null;
  return (
    <section ref={ref} role="dialog" aria-modal="true" aria-label={label} tabIndex={-1}>
      {children}
    </section>
  );
}

function DialogStackHarness() {
  const [outerOpen, setOuterOpen] = useState(true);
  const [innerOpen, setInnerOpen] = useState(true);

  return (
    <>
      <TestDialog open={outerOpen} label="Outer dialog">
        <button type="button">Outer action</button>
      </TestDialog>
      <TestDialog open={innerOpen} label="Nested dialog">
        <button type="button" onClick={() => {
          setOuterOpen(false);
          setInnerOpen(false);
        }}>Discard and close both</button>
      </TestDialog>
    </>
  );
}

describe("nested dialog scroll locking", () => {
  it("restores the original body overflow when both dialogs close together", () => {
    render(<DialogStackHarness />);
    expect(document.body.style.overflow).toBe("hidden");

    fireEvent.click(screen.getByRole("button", { name: "Discard and close both" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.body.style.overflow).toBe("");
  });
});
