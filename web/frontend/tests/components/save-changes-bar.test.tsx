import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SaveChangesBar } from "../../src/Components/Forms/SaveChangesBar";

describe("SaveChangesBar", () => {
  it("announces its region and invokes save and reset callbacks", () => {
    const onSave = vi.fn();
    const onReset = vi.fn();

    render(
      <SaveChangesBar
        label="Unsaved policy changes"
        detail="Two values changed"
        ariaLabel="Command access policy changes"
        onSave={onSave}
        onReset={onReset}
      />,
    );

    expect(screen.getByRole("region", { name: "Command access policy changes" })).toBeTruthy();
    expect(screen.getByText("Unsaved policy changes")).toBeTruthy();
    expect(screen.getByText("Two values changed")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Save Changes/ }));
    fireEvent.click(screen.getByRole("button", { name: /Reset/ }));
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it("disables writes while saving and exposes the saving label", () => {
    const onSave = vi.fn();
    const onReset = vi.fn();

    render(
      <SaveChangesBar
        label="Saving changes"
        ariaLabel="Command settings"
        saving
        onSave={onSave}
        onReset={onReset}
      />,
    );

    const save = screen.getByRole("button", { name: "Saving…" }) as HTMLButtonElement;
    const reset = screen.getByRole("button", { name: /Reset/ }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    expect(reset.disabled).toBe(true);
    fireEvent.click(save);
    expect(onSave).not.toHaveBeenCalled();
  });

  it("honours independent save and reset disabled states", () => {
    render(
      <SaveChangesBar
        label="No pending changes"
        ariaLabel="Command settings"
        saveDisabled
        resetDisabled
        onSave={vi.fn()}
        onReset={vi.fn()}
      />,
    );

    expect((screen.getByRole("button", { name: /Save Changes/ }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: /Reset/ }) as HTMLButtonElement).disabled).toBe(true);
  });
});
