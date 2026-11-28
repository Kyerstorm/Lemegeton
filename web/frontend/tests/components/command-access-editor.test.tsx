import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CommandAccessEditor } from "../../src/Components/Features/Commands/CommandAccessEditor";

describe("CommandAccessEditor", () => {
  it("focuses its close action and supports Escape to close", () => {
    const onClose = vi.fn();
    render(
      <>
        <button type="button">Open access editor</button>
        <CommandAccessEditor
          target="discover browse"
          loading
          error=""
          errorStatus={null}
          options={null}
          draft={null}
          dirty={false}
          saving={false}
          onRetry={vi.fn()}
          setDraft={vi.fn()}
          onClose={onClose}
          onReset={vi.fn()}
          onSave={vi.fn()}
        />
      </>,
    );

    const dialog = screen.getByRole("dialog", { name: /access for/i });
    const close = screen.getByRole("button", { name: "Close access editor" });
    expect(dialog).toBeTruthy();
    expect(document.activeElement).toBe(close);

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
