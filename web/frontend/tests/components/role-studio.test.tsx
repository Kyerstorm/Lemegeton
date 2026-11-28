import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RoleStudio } from "../../src/Components/Features/CustomRoles/RoleStudio";

describe("RoleStudio", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/custom-roles/");
    window.sessionStorage.clear();
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the editor shell and explains when no private picker link is present", async () => {
    const fetchMock = vi.mocked(fetch);
    const { container } = render(<RoleStudio />);

    expect(screen.getByRole("group", { name: "Lemegeton role studio" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Make it yours." })).toBeTruthy();
    expect(container.querySelector("#loading")).toBeTruthy();

    expect(await screen.findByText("No link found")).toBeTruthy();
    expect(screen.getByText(
      "Open this page from the Color picker button in /custom-role in Discord.",
    )).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("keeps the role editor unavailable until the picker has a valid session", async () => {
    const { container } = render(<RoleStudio />);

    expect(await screen.findByText("No link found")).toBeTruthy();
    expect(container.querySelector("#app")?.classList.contains("hidden")).toBe(true);
    expect(container.querySelector("#problem")?.classList.contains("hidden")).toBe(false);
    expect(container.querySelector("#loading")?.classList.contains("hidden")).toBe(true);
  });
});
