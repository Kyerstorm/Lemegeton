import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { ReceiptThankYou } from "../../src/Components/Feedback/ReceiptThankYou";

describe("ReceiptThankYou", () => {
  it("renders as a dialog and continues without navigating", () => {
    const onContinue = vi.fn();
    render(<ReceiptThankYou onContinue={onContinue} />);

    expect(screen.getByRole("dialog", { name: "Thank you." })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(onContinue).toHaveBeenCalledTimes(1);
  });

  it("traps focus, closes with Escape, and restores the opener", () => {
    function ThankYouHarness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>Open receipt note</button>
          {open ? <ReceiptThankYou onContinue={() => setOpen(false)} /> : null}
        </>
      );
    }

    render(<ThankYouHarness />);
    const trigger = screen.getByRole("button", { name: "Open receipt note" });
    fireEvent.click(trigger);

    const dialog = screen.getByRole("dialog", { name: "Thank you." });
    expect(dialog).toBeTruthy();
    const continueButton = screen.getByRole("button", { name: "Continue" });
    expect(document.activeElement).toBe(continueButton);

    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(continueButton);
    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.queryByRole("dialog", { name: "Thank you." })).toBeNull();
    expect(document.activeElement).toBe(trigger);
    expect(document.body.style.overflow).toBe("");
  });
});