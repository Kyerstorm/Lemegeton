import { fireEvent, render, screen } from "@testing-library/react";
import type { FormEvent } from "react";
import { describe, expect, it, vi } from "vitest";
import { Button } from "../../src/Components/UI/Button";

describe("Button", () => {
  it("defaults to a non-submitting button inside forms", () => {
    const onSubmit = vi.fn((event: FormEvent<HTMLFormElement>) => event.preventDefault());
    render(
      <form onSubmit={onSubmit}>
        <Button>Open settings</Button>
      </form>,
    );

    const button = screen.getByRole("button", { name: "Open settings" }) as HTMLButtonElement;
    expect(button.type).toBe("button");
    fireEvent.click(button);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("preserves an explicitly requested submit type", () => {
    render(
      <form>
        <Button type="submit">Save changes</Button>
      </form>,
    );

    expect((screen.getByRole("button", { name: "Save changes" }) as HTMLButtonElement).type).toBe("submit");
  });
});
