import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { Tabs } from "../../src/Components/UI/Tabs";

describe("Tabs", () => {
  const options = [
    { value: "overview", label: "Overview" },
    { value: "commands", label: "Commands" },
    { value: "archive", label: "Archive", disabled: true },
    { value: "settings", label: "Settings" },
  ] as const;

  it("reports click selection and exposes the active tab", () => {
    const onChange = vi.fn();
    render(<Tabs value="overview" options={options} onChange={onChange} label="Dashboard sections" />);

    expect(screen.getByRole("tab", { name: "Overview" }).getAttribute("aria-selected")).toBe("true");
    fireEvent.click(screen.getByRole("tab", { name: "Commands" }));
    expect(onChange).toHaveBeenCalledWith("commands");
  });

  it("moves with arrow keys, skips disabled tabs and wraps around", () => {
    function ControlledTabs() {
      const [value, setValue] = useState("commands");
      return <Tabs value={value} options={options} onChange={setValue} label="Dashboard sections" />;
    }

    render(<ControlledTabs />);
    const commands = screen.getByRole("tab", { name: "Commands" });
    commands.focus();
    fireEvent.keyDown(commands, { key: "ArrowRight" });
    const settings = screen.getByRole("tab", { name: "Settings" });
    expect(settings.getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(settings);

    fireEvent.keyDown(settings, { key: "ArrowRight" });
    const overview = screen.getByRole("tab", { name: "Overview" });
    expect(overview.getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(overview);

    fireEvent.keyDown(overview, { key: "ArrowLeft" });
    expect(settings.getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(settings);

    fireEvent.keyDown(settings, { key: "Home" });
    expect(overview.getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(overview);

    fireEvent.keyDown(overview, { key: "End" });
    expect(settings.getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(settings);
  });

  it("does not select disabled tabs", () => {
    const onChange = vi.fn();
    render(<Tabs value="commands" options={options} onChange={onChange} label="Dashboard sections" />);

    const archiveTab = screen.getByRole("tab", { name: "Archive" }) as HTMLButtonElement;
    expect(archiveTab.disabled).toBe(true);
    fireEvent.click(archiveTab);
    expect(onChange).not.toHaveBeenCalled();
  });
});
