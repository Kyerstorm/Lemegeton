export function number(value: number | null | undefined): string {
  return value == null || !Number.isFinite(Number(value)) ? "—" : Number(value).toLocaleString();
}
export function duration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(Number(seconds))) return "Unavailable";
  const value = Math.max(0, Number(seconds));
  const days = Math.floor(value / 86400);
  const hours = Math.floor((value % 86400) / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const secs = Math.floor(value % 60);
  return (days ? days + "d " : "") + hours + "h " + minutes + "m " + secs + "s";
}
export function timeAgo(value?: string): string {
  if (!value) return "Unknown time";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  const elapsed = Math.max(0, Math.floor((Date.now() - parsed.getTime()) / 1000));
  if (elapsed < 60) return "Just now";
  if (elapsed < 3600) return Math.floor(elapsed / 60) + "m ago";
  if (elapsed < 86400) return Math.floor(elapsed / 3600) + "h ago";
  return Math.floor(elapsed / 86400) + "d ago";
}
export function timestamp(value?: number): string {
  return value ? new Date(value * 1000).toLocaleString() : "Unavailable";
}
export function gatewayStatusLabel(status?: string, ready?: boolean): string {
  switch (status) {
    case "unknown":
      return "Unknown";
    case "offline":
      return "Offline";
    case "connecting":
      return "Connecting";
    case "degraded":
      return "Degraded";
    case "online":
      return ready === false ? "Not ready" : "Connected";
    default:
      return ready ? "Connected" : "Not ready";
  }
}

export function gatewayStatusDescription(status?: string, reason?: string): string {
  switch (status) {
    case "unknown":
      return reason || "Live bot health is unavailable.";
    case "offline":
      return "The Discord gateway disconnected after a previous successful connection. The management bridge may still respond.";
    case "connecting":
      return "The bot process has not reached Discord gateway readiness yet.";
    case "degraded":
      return "The Discord gateway is connected, but a runtime dependency or gateway latency is degraded.";
    case "online":
      return "The Discord gateway is connected and the runtime reports healthy.";
    default:
      return "The bot has not reported a current gateway state.";
  }
}
