import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Input } from "../../src/Components/UI/Input";
import { Select } from "../../src/Components/UI/Select";

describe("shared control hints", () => {
  it("associates Input hints without replacing an existing description or label", () => {
    render(
      <>
        <span id="search-shortcut">Press / to focus search.</span>
        <Input
          id="command-search"
          label="Search commands"
          hint="Search by name or category."
          aria-describedby="search-shortcut"
        />
      </>,
    );

    const input = screen.getByRole("textbox", { name: "Search commands" });
    const ids = input.getAttribute("aria-describedby")?.split(" ") ?? [];
    expect(ids).toHaveLength(2);
    expect(document.getElementById(ids[0])?.textContent).toBe("Press / to focus search.");
    expect(document.getElementById(ids[1])?.textContent).toBe("Search by name or category.");
  });

  it("associates Select hints with its control without adding them to the label", () => {
    render(
      <Select
        id="command-category"
        label="Category"
        hint="Choose which commands to show."
        value="all"
        onChange={() => undefined}
        options={[{ value: "all", label: "All categories" }]}
      />,
    );

    const select = screen.getByRole("combobox", { name: "Category" });
    const hintId = select.getAttribute("aria-describedby");
    expect(hintId).toBeTruthy();
    expect(document.getElementById(hintId!)?.textContent).toBe("Choose which commands to show.");
  });
});
