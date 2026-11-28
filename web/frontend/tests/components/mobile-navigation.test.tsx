import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { Sidebar } from "../../src/Components/Layout/Sidebar";
import { MobileNavigationTrigger } from "../../src/Components/Layout/MobileNavigation";

vi.mock("../../src/Components/UI", () => ({ Watcher: () => null }));
vi.mock("../../src/Components/UI/LogoTraceLoader", () => ({ LogoTraceLoader: () => null }));

function SidebarHarness() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <MobileNavigationTrigger open={open} onToggle={() => setOpen(value => !value)} />
      <button type="button" onClick={() => setOpen(false)}>Close drawer</button>
      <Sidebar
        page="overview"
        mobileNav={open}
        commandCount={0}
        runtimeOnline={false}
        botReady={false}
        botModerator={false}
        canManageServer
        runtimeStatus="UNKNOWN"
        onNavigate={vi.fn()}
        onCloseNavigation={() => setOpen(false)}
        onLogout={vi.fn()}
      />
    </>
  );
}

describe("mobile dashboard navigation", () => {
  it("announces the open drawer as a modal and moves focus into it", () => {
    render(<SidebarHarness />);
    const trigger = screen.getByRole("button", { name: "Open navigation" });
    fireEvent.click(trigger);

    const dialog = screen.getByRole("dialog", { name: "Dashboard navigation" });
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    expect(trigger.getAttribute("aria-controls")).toBe("sidebar");
    expect(trigger.getAttribute("aria-label")).toBe("Close navigation");
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(document.activeElement).toBe(dialog.querySelector(".main-nav .nav-item"));
  });

  it("keeps keyboard focus inside the open drawer", () => {
    render(<SidebarHarness />);
    const trigger = screen.getByRole("button", { name: "Open navigation" });
    fireEvent.click(trigger);

    const dialog = screen.getByRole("dialog", { name: "Dashboard navigation" });
    const first = dialog.querySelector<HTMLAnchorElement>("a[href]");
    const last = within(dialog).getByRole("button", { name: /sign out/i });
    expect(first).not.toBeNull();

    first?.focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(last);

    last.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(first);
  });

  it("restores focus to the menu trigger when the drawer closes", () => {
    render(<SidebarHarness />);

    const trigger = screen.getByRole("button", { name: "Open navigation" });
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("button", { name: "Close drawer" }));

    expect(screen.queryByRole("dialog", { name: "Dashboard navigation" })).toBeNull();
    expect(document.activeElement).toBe(trigger);
    expect(document.body.style.overflow).toBe("");
  });
  it("closes on Escape and restores focus to the menu trigger", () => {
    render(<SidebarHarness />);

    const trigger = screen.getByRole("button", { name: "Open navigation" });
    fireEvent.click(trigger);
    expect(screen.getByRole("dialog", { name: "Dashboard navigation" })).toBeTruthy();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.queryByRole("dialog", { name: "Dashboard navigation" })).toBeNull();
    expect(document.activeElement).toBe(trigger);
    expect(document.body.style.overflow).toBe("");
  });

});