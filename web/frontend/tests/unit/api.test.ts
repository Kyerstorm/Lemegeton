import { afterEach, describe, expect, it, vi } from "vitest";
import { ACTION_FEEDBACK_EVENT, api, errorMessage, reportRuntimeIssue, type ActionFeedbackDetail, type DashboardApiError } from "../../src/Lib/api";

function jsonResponse(value: unknown, status = 200): Response {
  return {
    ok: true,
    status,
    headers: new Headers(),
    json: async () => value,
  } as Response;
}

describe("dashboard API request coordination", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shares an in-flight GET and allows a later refresh", async () => {
    let resolveResponse: ((response: Response) => void) | undefined;
    const fetchMock = vi.fn(() => new Promise<Response>((resolve) => {
      resolveResponse = resolve;
    }));
    vi.stubGlobal("fetch", fetchMock);

    const first = api<{ revision: string }>("/api/guilds/123/commands", "csrf");
    const second = api<{ revision: string }>("/api/guilds/123/commands", "csrf");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    resolveResponse?.(jsonResponse({ revision: "one" }));
    const [firstResult, secondResult] = await Promise.all([first, second]);

    expect(firstResult.revision).toBe("one");
    expect(secondResult.revision).toBe("one");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    fetchMock.mockResolvedValueOnce(jsonResponse({ revision: "two" }));
    const refreshed = await api<{ revision: string }>("/api/guilds/123/commands", "csrf");
    expect(refreshed.revision).toBe("two");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not coalesce mutations", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ ok: true }))
      .mockResolvedValueOnce(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await Promise.all([
      api("/api/guilds/123/commands", "csrf", { method: "PUT", body: "{}" }),
      api("/api/guilds/123/commands", "csrf", { method: "PUT", body: "{}" }),
    ]);

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
  it("keeps server diagnostics out of the UI and returns a real issue reference", async () => {
    const reference = "a".repeat(40);
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        headers: new Headers(),
        json: async () => ({ error: "Internal database stack trace and secret details" }),
      } as Response)
      .mockResolvedValueOnce(jsonResponse({ issue_reference: reference }, 201));
    vi.stubGlobal("fetch", fetchMock);

    let failure: DashboardApiError | undefined;
    try {
      await api(
        "/api/guilds/12345678901234567/archive-settings",
        "csrf-token",
        { method: "PUT", body: "{}" },
      );
    } catch (error) {
      failure = error as DashboardApiError;
    }

    expect(failure).toBeDefined();
    expect(failure?.message).toBe("Lemegeton could not complete this request. Please retry.");
    expect(failure?.message).not.toContain("Internal database");
    expect(failure?.issueReference).toBe(reference);
    expect(errorMessage(failure)).toContain("Please open a GitHub issue");
    expect(errorMessage(failure)).toContain(reference);
    expect(errorMessage(failure)).not.toContain("https://");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/guilds/12345678901234567/issues");
  });

  it("announces mutation progress and confirmed save completion", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ settings: {} }));
    vi.stubGlobal("fetch", fetchMock);
    const feedback: ActionFeedbackDetail[] = [];
    const listener = (event: Event) => feedback.push((event as CustomEvent<ActionFeedbackDetail>).detail);
    window.addEventListener(ACTION_FEEDBACK_EVENT, listener);

    try {
      await api(
        "/api/guilds/12345678901234567/archive-settings",
        "csrf-token",
        { method: "PUT", body: "{}" },
      );
    } finally {
      window.removeEventListener(ACTION_FEEDBACK_EVENT, listener);
    }

    expect(feedback).toHaveLength(2);
    expect(feedback[0]?.phase).toBe("start");
    expect(feedback[0]?.message).toBe("Saving changes…");
    expect(feedback[1]?.phase).toBe("finish");
    expect(feedback[1]?.successMessage).toBe("Archive settings saved.");
  });

  it("reports unhandled dashboard runtime failures through the authenticated issue route", async () => {
    const reference = "b".repeat(40);
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ issue_reference: reference }, 201));
    vi.stubGlobal("fetch", fetchMock);

    const result = await reportRuntimeIssue(
      "12345678901234567",
      "csrf-token",
      "dashboard-runtime",
      "A browser component failed.",
      "Error: A browser component failed.",
    );

    expect(result).toBe(reference);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/guilds/12345678901234567/issues");
    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(request.headers).toMatchObject({ "X-CSRF-Token": "csrf-token" });
    expect(JSON.parse(String(request.body))).toMatchObject({
      component: "dashboard-runtime",
      path: "/api/guilds/12345678901234567/dashboard-runtime",
      message: "A browser component failed.",
    });
  });

});
