export class DashboardApiError extends Error {
  constructor(message: string, readonly status: number, readonly retryAfter?: number) {
    super(message);
    this.name = "DashboardApiError";
  }
}

export function requestErrorStatus(value: unknown): number | null {
  return value instanceof DashboardApiError ? value.status : null;
}

export function errorMessage(value: unknown): string {
  return value instanceof Error ? value.message : "Something went wrong. Please retry.";
}
