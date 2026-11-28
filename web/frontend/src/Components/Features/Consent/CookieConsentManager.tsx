"use client";

import { useEffect, useState } from "react";

type CookieStatus = {
  saved: boolean;
  remember_server: boolean;
  consent_version: string;
};

export function CookieConsentManager() {
  const [ready, setReady] = useState(false);
  const [saved, setSaved] = useState(false);
  const [open, setOpen] = useState(false);
  const [configuring, setConfiguring] = useState(false);
  const [rememberServer, setRememberServer] = useState(false);
  const [savedRememberServer, setSavedRememberServer] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    fetch("/api/cookies", { credentials: "same-origin", cache: "no-store" })
      .then(async response => {
        if (!response.ok) throw new Error("Cookie preferences could not be checked.");
        return response.json() as Promise<CookieStatus>;
      })
      .then(status => {
        if (!active) return;
        const hasCurrentChoice = status.saved === true;
        setSaved(hasCurrentChoice);
        setRememberServer(hasCurrentChoice && status.remember_server === true);
        setSavedRememberServer(hasCurrentChoice && status.remember_server === true);
        setOpen(!hasCurrentChoice);
      })
      .catch(() => {
        if (!active) return;
        setOpen(true);
        setError("Your current choice could not be checked. Optional storage stays off until your choice is saved.");
      })
      .finally(() => { if (active) setReady(true); });
    return () => { active = false; };
  }, []);

  const save = async (remember: boolean) => {
    if (saving) return;
    setSaving(true);
    setError("");
    try {
      const response = await fetch("/api/cookies", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ remember_server: remember }),
      });
      const result = await response.json().catch(() => ({})) as { saved?: boolean; error?: string };
      if (!response.ok || result.saved !== true) {
        throw new Error(result.error || "Your cookie choice could not be saved. Please retry.");
      }
      setSaved(true);
      setRememberServer(remember);
      setSavedRememberServer(remember);
      if (!remember) {
        try { window.localStorage.removeItem("lemegeton:selected-guild"); } catch { /* browser storage may be disabled */ }
      }
      setOpen(false);
      setConfiguring(false);
      window.dispatchEvent(new CustomEvent("lemegeton:cookie-consent", {
        detail: { rememberServer: remember },
      }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Your cookie choice could not be saved. Please retry.");
    } finally {
      setSaving(false);
    }
  };

  if (!ready) return null;

  return (
    <>
      {open ? (
        <aside className="cookie-consent" aria-label="Cookie and browser storage preferences">
          <div className="cookie-consent-inner">
            <div className="cookie-consent-copy">
              <p className="cookie-consent-eyebrow"><span /> PRIVACY / YOUR CHOICE</p>
              <h2 id="cookie-consent-title">Your privacy, your call.</h2>
              <p>
                Lemegeton uses essential cookies to secure sign-in and remember this choice.
                Optional storage can remember your last selected Discord server. It is off until you allow it.
                Read our <a href="/privacy-policy/">Privacy Policy</a>.
              </p>
            </div>

            {configuring ? (
              <div className="cookie-consent-options">
                <div className="cookie-consent-option cookie-consent-essential">
                  <span className="cookie-consent-option-state">ALWAYS ACTIVE</span>
                  <div>
                    <strong>Essential cookies</strong>
                    <p>Session security, Discord OAuth sign-in protection, and saving your privacy choice. These are required for the requested website features.</p>
                  </div>
                </div>
                <label className="cookie-consent-option cookie-consent-toggle">
                  <span className="cookie-consent-switch">
                    <input
                      type="checkbox"
                      checked={rememberServer}
                      onChange={event => setRememberServer(event.target.checked)}
                    />
                    <span aria-hidden="true" />
                  </span>
                  <span>
                    <strong>Remember my selected server</strong>
                    <p>Stores your last selected Discord server in this browser so it can be restored next time. The dashboard works without it.</p>
                  </span>
                </label>
                <p className="cookie-consent-note">No analytics or advertising cookies are currently used by the dashboard.</p>
              </div>
            ) : null}

            {error ? <p className="cookie-consent-error" role="alert">{error}</p> : null}

            <div className="cookie-consent-actions">
              {configuring ? (
                <>
                  <button type="button" className="cookie-consent-button" disabled={saving} onClick={() => {
                    setConfiguring(false);
                    setRememberServer(savedRememberServer);
                    setError("");
                    if (saved) setOpen(false);
                  }}>Cancel</button>
                  <button type="button" className="cookie-consent-button cookie-consent-primary" disabled={saving} onClick={() => void save(rememberServer)}>
                    {saving ? "Saving…" : "Save choices"}
                  </button>
                </>
              ) : (
                <>
                  <button type="button" className="cookie-consent-button cookie-consent-primary" disabled={saving} onClick={() => void save(true)}>Allow optional</button>
                  <button type="button" className="cookie-consent-button cookie-consent-primary" disabled={saving} onClick={() => void save(false)}>Reject optional</button>
                  <button type="button" className="cookie-consent-button" disabled={saving} onClick={() => {
                    setConfiguring(true);
                    setError("");
                  }}>Configure</button>
                </>
              )}
            </div>
          </div>
        </aside>
      ) : null}
      {saved && !open ? (
        <button
          type="button"
          className="cookie-consent-reopen"
          onClick={() => {
            setRememberServer(savedRememberServer);
            setConfiguring(true);
            setOpen(true);
          }}
        >
          Cookie settings
        </button>
      ) : null}
    </>
  );
}
