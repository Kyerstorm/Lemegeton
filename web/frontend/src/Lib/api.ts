export class DashboardApiError extends Error {
  issueReference: string | null = null;

  constructor(
    message: string,
    readonly status: number,
    readonly retryAfter?: number,
    readonly diagnosticMessage?: string,
  ) {
    super(message);
    this.name = "DashboardApiError";
  }
}

export const ACTION_FEEDBACK_EVENT = "lemegeton:action-feedback";

export interface ActionFeedbackDetail {
  id: number;
  phase: "start" | "finish";
  message: string;
  target: HTMLElement | null;
  successMessage?: string;
}

function dispatchActionFeedback(detail: ActionFeedbackDetail): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent<ActionFeedbackDetail>(ACTION_FEEDBACK_EVENT, { detail }));
  }
}

function actionTarget(): HTMLElement | null {
  if (typeof document === "undefined" || !(document.activeElement instanceof HTMLElement)) return null;
  return document.activeElement.closest<HTMLElement>("button,[role='button'],[role='menuitem']");
}

function successMessage(path: string, method: string, status: number): string | undefined {
  if (status === 202) return "Request accepted. Processing in the background.";
  const route = path.split("?")[0] || path;
  if (/\/api\/guilds\/\d{17,20}\/(?:sync|reset|commands|command-access(?:\/[^/]+)?)$/.test(route)
    || route === "/api/logout") return undefined;
  if (method === "PUT" && /\/archive-settings$/.test(route)) return "Archive settings saved.";
  if (method === "PUT" && /\/settings$/.test(route)) return "Server settings saved.";
  if (method === "POST" && route === "/api/consent") return "Agreement saved.";
  if (method === "POST" && route === "/api/cookies") return "Preferences saved.";
  return method === "DELETE" ? "Deleted successfully." : method === "POST" ? "Action completed." : "Changes saved.";
}

export async function reportRuntimeIssue(
  guildId: string,
  csrf: string,
  component: string,
  message: string,
  stack: string,
): Promise<string | null> {
  const safeComponent = component.replace(/[^a-z0-9._-]/gi, "").slice(0, 80) || "dashboard-runtime";
  return reportDashboardIssue(
    "/api/guilds/" + encodeURIComponent(guildId) + "/" + safeComponent,
    csrf,
    message,
    stack,
  );
}

async function reportDashboardIssue(
  path: string,
  csrf: string,
  message: string,
  stack: string,
): Promise<string | null> {
  const route = path.split("?")[0] || path;
  const guild = /^\/api\/guilds\/(\d{17,20})(?:\/|$)/.exec(route)?.[1];
  if (!guild || route.endsWith("/issues")) return null;

  const component = (route.split("/").filter(Boolean)[3] || "dashboard")
    .replace(/[^a-z0-9._-]/gi, "")
    .slice(0, 80) || "dashboard";
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5_000);
  try {
    const response = await fetch("/api/guilds/" + encodeURIComponent(guild) + "/issues", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify({
        component,
        path: route.slice(0, 512),
        message: message.slice(0, 2_000),
        stack: stack.slice(0, 12_000),
      }),
      signal: controller.signal,
    });
    if (!response.ok) return null;
    const payload = await response.json() as { issue_reference?: unknown };
    return typeof payload.issue_reference === "string" && /^[a-f0-9]{40}$/i.test(payload.issue_reference)
      ? payload.issue_reference
      : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

const inFlightGetRequests = new Map<string, Promise<unknown>>();
const REQUEST_TIMEOUT_MS = 15_000;

async function executeApiRequest<T>(path: string, csrf: string, init: RequestInit, onResponse?: (status: number) => void): Promise<T> {
  const method = (init.method || "GET").toUpperCase();
  const headers = new Headers(init.headers || {});

  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    headers.set("Content-Type", "application/json");
    headers.set("X-CSRF-Token", csrf);
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const abortFromCaller = () => controller.abort();
  if (init.signal?.aborted) controller.abort();
  else init.signal?.addEventListener("abort", abortFromCaller, { once: true });

  try {
    let response: Response;
    try {
      response = await fetch(path, {
        ...init,
        method,
        headers,
        credentials: "same-origin",
        cache: "no-store",
        signal: controller.signal,
      });
    } catch (error) {
      if (init.signal?.aborted) throw error;
      if (controller.signal.aborted) {
        throw new DashboardApiError(
          "The dashboard request timed out. Check your connection and retry.",
          0,
        );
      }
      throw new DashboardApiError(
        "The dashboard is offline or unreachable. Check your connection and retry.",
        0,
      );
    }

    if (response.status === 401) {
      window.location.assign("/login");
      throw new DashboardApiError("Your session expired. Sign in again.", 401);
    }

    let data: { error?: unknown } = {};
    try {
      data = await response.json() as { error?: unknown };
    } catch (error) {
      if (controller.signal.aborted) {
        if (init.signal?.aborted) throw error;
        throw new DashboardApiError(
          "The dashboard request timed out. Check your connection and retry.",
          0,
        );
      }
    }

    const serverMessage = typeof data.error === "string" && data.error.trim()
      ? data.error
      : undefined;

    if (!response.ok) {
      if (response.status === 403) {
        throw new DashboardApiError(
          serverMessage || "Your account is not authorized to perform this action. Check the required Discord server or dashboard-owner permissions.",
          403,
          undefined,
          serverMessage,
        );
      }

      if (response.status === 429) {
        const retryHeader = response.headers.get("retry-after");
        const numericRetry = retryHeader ? Number(retryHeader) : Number.NaN;
        const retryDate = retryHeader && !Number.isFinite(numericRetry)
          ? Date.parse(retryHeader)
          : Number.NaN;
        const retryAfter = Number.isFinite(numericRetry)
          ? Math.max(0, numericRetry)
          : Number.isFinite(retryDate)
            ? Math.max(0, Math.ceil((retryDate - Date.now()) / 1000))
            : undefined;
        const wait = retryAfter === undefined
          ? " Wait briefly before trying again."
          : " Try again in " + retryAfter + " seconds.";

        throw new DashboardApiError("The dashboard is rate limited." + wait, 429, retryAfter, serverMessage);
      }

      const unexpected = response.status >= 500;
      const diagnosticMessage = serverMessage || ("Dashboard " + method + " request failed with status " + response.status + ".");
      const failure = new DashboardApiError(
        unexpected
          ? "Lemegeton could not complete this request. Please retry."
          : serverMessage || ("Request failed (" + response.status + ")."),
        response.status,
        undefined,
        diagnosticMessage,
      );
      if (unexpected) {
        failure.issueReference = await reportDashboardIssue(path, csrf, diagnosticMessage, failure.stack || "");
      }
      throw failure;
    }

    onResponse?.(response.status);
    return data as T;
  } finally {
    clearTimeout(timeout);
    init.signal?.removeEventListener("abort", abortFromCaller);
  }
}

export function api<T>(path: string, csrf = "", init: RequestInit = {}): Promise<T> {
  const method = (init.method || "GET").toUpperCase();
  if (method !== "GET" || init.signal) {
    if (!["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
      return executeApiRequest<T>(path, csrf, { ...init, method });
    }

    const id = Date.now() + Math.floor(Math.random() * 1_000);
    const target = actionTarget();
    dispatchActionFeedback({
      id,
      phase: "start",
      message: method === "PUT" ? "Saving changes…" : "Processing request…",
      target,
    });
    let status = 200;
    return executeApiRequest<T>(path, csrf, { ...init, method }, responseStatus => {
      status = responseStatus;
    }).then(
      result => {
        dispatchActionFeedback({
          id,
          phase: "finish",
          message: "",
          target,
          successMessage: successMessage(path, method, status),
        });
        return result;
      },
      error => {
        dispatchActionFeedback({ id, phase: "finish", message: "", target });
        throw error;
      },
    );
  }

  const requestHeaders: string[] = [];
  new Headers(init.headers || {}).forEach((value, name) => {
    requestHeaders.push(name.toLowerCase() + ":" + value);
  });
  requestHeaders.sort();

  const key = JSON.stringify([
    path,
    csrf,
    requestHeaders,
    init.mode || null,
    init.redirect || null,
    init.referrer || null,
    init.referrerPolicy || null,
    init.integrity || null,
    init.keepalive || false,
  ]);
  const existing = inFlightGetRequests.get(key);
  if (existing) return existing as Promise<T>;

  const request = executeApiRequest<T>(path, csrf, { ...init, method });
  inFlightGetRequests.set(key, request);
  const clearRequest = () => {
    if (inFlightGetRequests.get(key) === request) inFlightGetRequests.delete(key);
  };
  void request.then(clearRequest, clearRequest);
  return request;
}

export function requestErrorStatus(value: unknown): number | null {
  return value instanceof DashboardApiError ? value.status : null;
}

export function errorMessage(value: unknown): string {
  const message = value instanceof Error ? value.message : "Something went wrong. Please retry.";
  if (value instanceof DashboardApiError && value.status >= 500) {
    const reference = value.issueReference ? " Reference: " + value.issueReference + "." : "";
    return message + reference + " Please open a GitHub issue if this continues.";
  }
  return message;
}
