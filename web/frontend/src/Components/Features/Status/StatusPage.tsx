"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Icon } from "../../Icons";

type StatusLevel = "operational" | "degraded" | "major_outage" | "unknown";

interface ServiceComponent {
  id: string;
  name: string;
  status: StatusLevel;
  detail: string;
  latency_ms?: number | null;
}

interface StatusSnapshot {
  status: StatusLevel;
  observed_at: number;
  components: ServiceComponent[];
}

const POLL_INTERVAL = 30_000;

const STATUS_LABELS: Record<StatusLevel, string> = {
  operational: "Operational",
  degraded: "Degraded",
  major_outage: "Major outage",
  unknown: "Unknown",
};

function isStatusLevel(value: unknown): value is StatusLevel {
  return value === "operational" || value === "degraded" || value === "major_outage" || value === "unknown";
}

function isStatusSnapshot(value: unknown): value is StatusSnapshot {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<StatusSnapshot>;
  return isStatusLevel(candidate.status)
    && typeof candidate.observed_at === "number"
    && Array.isArray(candidate.components)
    && candidate.components.every((component) => (
      Boolean(component)
      && typeof component.id === "string"
      && typeof component.name === "string"
      && isStatusLevel(component.status)
      && typeof component.detail === "string"
    ));
}

function formatTimestamp(timestamp: number): string {
  return new Intl.DateTimeFormat("en-IE", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: "UTC",
    timeZoneName: "short",
  }).format(new Date(timestamp * 1000));
}

function statusHeading(status: StatusLevel, unavailable: boolean, loading: boolean): string {
  if (loading) return "Checking Lemegeton systems";
  if (unavailable) return "Live status unavailable";
  switch (status) {
    case "operational": return "All monitored systems operational";
    case "degraded": return "Some systems need attention";
    case "major_outage": return "A service disruption is active";
    default: return "System status could not be verified";
  }
}

function statusDescription(status: StatusLevel, unavailable: boolean, loading: boolean, noComponents: boolean): string {
  if (loading) return "Retrieving the latest checks from the dashboard and bot runtime.";
  if (unavailable) return "The status service could not be reached. Try refreshing the live checks.";
  if (noComponents) return "No monitored components are currently published, so system health cannot be confirmed.";
  switch (status) {
    case "operational": return "The checks currently available to this page are responding normally.";
    case "degraded": return "One or more checks are delayed, starting up, or could not be confirmed.";
    case "major_outage": return "A monitored service is reporting an outage. Check the affected component below.";
    default: return "At least one service could not be verified. Its state is shown as unknown rather than assumed operational.";
  }
}

function ComponentRow({ component, index }: { component: ServiceComponent; index: number }) {
  return (
    <article className="status-component" style={{ animationDelay: `${index * 65}ms` }}>
      <span className={`status-component-indicator status-component-indicator--${component.status}`} aria-hidden="true" />
      <div className="status-component-copy">
        <strong>{component.name}</strong>
        <small>{component.detail}</small>
      </div>
      <div className="status-component-state">
        {typeof component.latency_ms === "number" ? (
          <span className="status-latency">{component.latency_ms} ms</span>
        ) : null}
        <span className={`status-state status-state--${component.status}`}>
          {STATUS_LABELS[component.status]}
        </span>
      </div>
    </article>
  );
}

export function StatusPage() {
  const [snapshot, setSnapshot] = useState<StatusSnapshot | null>(null);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const inFlight = useRef(false);

  const refresh = useCallback(async (quiet = false) => {
    if (inFlight.current) return;
    inFlight.current = true;
    if (!quiet) setRefreshing(true);

    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 15_000);
    try {
      const response = await fetch("/api/status", { cache: "no-store", signal: controller.signal });
      if (!response.ok) throw new Error("Status request failed.");
      const payload: unknown = await response.json();
      if (!isStatusSnapshot(payload)) throw new Error("Status response was invalid.");
      setSnapshot(payload);
      setError("");
    } catch {
      setError("The latest live checks could not be retrieved.");
    } finally {
      window.clearTimeout(timeout);
      inFlight.current = false;
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const interval = window.setInterval(() => void refresh(true), POLL_INTERVAL);
    return () => window.clearInterval(interval);
  }, [refresh]);

  const noComponents = Boolean(snapshot && snapshot.components.length === 0);
  const status = noComponents ? "unknown" : snapshot?.status ?? "unknown";
  const loading = !snapshot && !error;
  const unavailable = !snapshot && Boolean(error);
  const stale = Boolean(snapshot && error);

  return (
    <main className="status-page">
      <div className="status-page-grid" aria-hidden="true" />
      <div className="status-page-shell">
        <header className="status-header">
          <a className="status-brand" href="/" aria-label="Lemegeton dashboard">
            <img src="/brand/lemegeton.svg" alt="" width="34" height="34" />
            <span>
              <strong>LEMEGETON</strong>
              <small>PUBLIC SYSTEM STATUS</small>
            </span>
          </a>
          <nav className="status-public-links" aria-label="Public navigation">
            <a className="status-guide-link" href="/how-it-works">How it works</a>
            <a className="status-dashboard-link" href="/">
              Dashboard <Icon name="arrow-up-right" size={13} />
            </a>
          </nav>
        </header>

        <section className={`status-hero status-hero--${status}`} aria-live="polite">
          <div className="status-hero-copy">
            <p className="status-eyebrow"><span className="status-live-dot" /> LIVE SERVICE CHECKS <span>/ 30 SEC</span></p>
            <h1>{statusHeading(status, unavailable, loading)}</h1>
            <p className="status-hero-description">{statusDescription(status, unavailable, loading, noComponents)}</p>
            {stale ? <p className="status-stale-note">Showing the last successful check. The latest refresh failed.</p> : null}
            {error && !snapshot ? <p className="status-stale-note">{error}</p> : null}
          </div>
          <div className="status-hero-art" aria-hidden="true">
            <span className="status-orbit status-orbit--outer" />
            <span className="status-orbit status-orbit--middle" />
            <span className="status-orbit status-orbit--inner" />
            <span className="status-orbit-core"><span /></span>
          </div>
          <div className="status-hero-footer">
            <span className={`status-state status-state--${status}`}>
              <i aria-hidden="true" /> {loading ? "Checking" : unavailable ? "Unavailable" : STATUS_LABELS[status]}
            </span>
            <div className="status-refresh-meta">
              <span>
                {snapshot
                  ? `${stale ? "LAST SUCCESSFUL CHECK" : "LAST UPDATED"} · ${formatTimestamp(snapshot.observed_at)}`
                  : "WAITING FOR FIRST CHECK"}
              </span>
              <button className="status-refresh-button" type="button" onClick={() => void refresh()} disabled={refreshing}>
                <Icon name="refresh" size={15} className={refreshing ? "status-refresh-icon is-spinning" : "status-refresh-icon"} />
                {refreshing ? "Checking" : "Refresh"}
              </button>
            </div>
          </div>
        </section>

        <section className="status-section" aria-labelledby="status-components-title">
          <div className="status-section-heading">
            <div>
              <p className="status-eyebrow">SERVICE MONITOR / 01</p>
              <h2 id="status-components-title">Component status</h2>
            </div>
            <span className="status-section-meta">LIVE SNAPSHOT</span>
          </div>

          <div className="status-component-list">
            {snapshot ? snapshot.components.length > 0 ? snapshot.components.map((component, index) => (
              <ComponentRow key={component.id} component={component} index={index} />
            )) : (
              <div className="status-empty" role="status">
                <p>No monitored component checks are currently published.</p>
                <button className="status-refresh-button" type="button" onClick={() => void refresh()} disabled={refreshing}>
                  <Icon name="refresh" size={15} className={refreshing ? "status-refresh-icon is-spinning" : "status-refresh-icon"} />
                  {refreshing ? "Checking" : "Refresh checks"}
                </button>
              </div>
            ) : (
              <div className="status-loading" role="status">
                <span className="status-loading-line" />
                <span className="status-loading-line" />
                <span className="status-loading-copy">{unavailable ? "Live component checks are unavailable." : "Checking monitored services…"}</span>
              </div>
            )}
          </div>
        </section>

        <section className="status-info-grid">
          <article className="status-info-card">
            <p className="status-eyebrow">INCIDENTS / 02</p>
            <div className="status-info-title">
              <h2>Incident updates</h2>
              <Icon name="arrow-up-right" size={14} className="status-info-mark" />
            </div>
            <p>Incident publishing is not connected yet. When incident tracking is enabled, updates and resolution timelines will appear here.</p>
            <span className="status-info-foot">INCIDENT HISTORY · NOT AVAILABLE</span>
          </article>
          <article className="status-info-card">
            <p className="status-eyebrow">AVAILABILITY / 03</p>
            <div className="status-info-title">
              <h2>Uptime history</h2>
              <span className="status-uptime-value">—</span>
            </div>
            <p>Historical sampling has not started. Uptime percentages will be shown once there is measured data to support them.</p>
            <span className="status-info-foot">30 / 90 DAY METRICS · NOT MEASURED</span>
          </article>
        </section>

        <footer className="status-footer">
          <span>LEMEGETON / STATUS</span>
          <span>LIVE CHECKS · UTC · AUTO-REFRESH 30S</span>
          <a href="/">RETURN TO DASHBOARD <Icon name="arrow-up-right" size={12} /></a>
        </footer>
      </div>
    </main>
  );
}
