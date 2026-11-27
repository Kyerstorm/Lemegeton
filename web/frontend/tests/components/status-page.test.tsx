import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StatusPage } from "../../src/Components/Features/Status/StatusPage";

const snapshot = {
  status: "operational",
  observed_at: 1795680000,
  components: [{
    id: "dashboard-api",
    name: "Dashboard API",
    status: "operational",
    detail: "Authenticated dashboard requests are responding.",
    latency_ms: 28,
  }],
};

function response(body: unknown, ok = true): Response {
  return { ok, json: async () => body } as Response;
}

afterEach(() => vi.unstubAllGlobals());

describe("StatusPage", () => {
  it("renders live response fields and refreshes when requested", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(snapshot));
    vi.stubGlobal("fetch", fetchMock);

    render(<StatusPage />);
    expect(await screen.findByRole("heading", { name: "All monitored systems operational" })).toBeTruthy();
    expect(screen.getByText("Dashboard API")).toBeTruthy();
    expect(screen.getByText("28 ms")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });

  it("reports unavailable for malformed status payloads instead of implying health", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({
      status: "healthy",
      observed_at: 1795680000,
      components: [],
    }));
    vi.stubGlobal("fetch", fetchMock);

    render(<StatusPage />);
    expect(await screen.findByRole("heading", { name: "Live status unavailable" })).toBeTruthy();
    expect(screen.getByText("The latest live checks could not be retrieved.")).toBeTruthy();
    expect(screen.getByText("Live component checks are unavailable.")).toBeTruthy();
  });

  it("does not report an empty component inventory as operational", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({
      status: "operational",
      observed_at: 1795680000,
      components: [],
    }));
    vi.stubGlobal("fetch", fetchMock);

    render(<StatusPage />);
    expect(await screen.findByRole("heading", { name: "System status could not be verified" })).toBeTruthy();
    expect(screen.getByText("No monitored components are currently published, so system health cannot be confirmed.")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain("No monitored component checks are currently published.");
    fireEvent.click(screen.getByRole("button", { name: "Refresh checks" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });

  it("keeps the last successful snapshot visible when a later refresh fails", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(snapshot))
      .mockRejectedValueOnce(new Error("network unavailable"));
    vi.stubGlobal("fetch", fetchMock);

    render(<StatusPage />);
    expect(await screen.findByText("Dashboard API")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(await screen.findByText("Showing the last successful check. The latest refresh failed.")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "All monitored systems operational" })).toBeTruthy();
    expect(screen.getByText("Dashboard API")).toBeTruthy();
  });
});
