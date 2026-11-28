"use client";

import { useEffect, useState } from "react";
import { Icon } from "../../Icons";
import { BrandMark } from "../../Brand/BrandMark";
import { SceneLoader } from "../../Three/SceneLoader";

const POLICIES = [
  { label: "Copyright & complaints", href: "/copyright-complaints" },
  { label: "DMCA", href: "/dmca" },
  { label: "Full policy index", href: "https://github.com/Kyerstorm/Lemegeton/blob/lemegeton-v3/docs/legal/README.md" },
];

export function LoginScreen() {
  const [cancelled, setCancelled] = useState(false);

  useEffect(() => {
    setCancelled(new URLSearchParams(window.location.search).get("error") === "cancelled");
  }, []);

  return (
    <main className="login-v2">
      <header className="login-v2-topline">
        <a className="login-v2-brand" href="/" aria-label="Lemegeton home">
          <BrandMark size={34} />
          <span>
            <strong>LEMEGETON</strong>
            <small>CONTROL PLANE</small>
          </span>
        </a>
        <nav className="login-v2-version" aria-label="Public links" style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
          <a href="/how-it-works">HOW IT WORKS</a>
          <a href="/github" target="_blank" rel="noreferrer">GITHUB <Icon name="arrow-up-right" size={11} /></a>
        </nav>
      </header>

      <section className="login-v2-layout">
        <div className="login-v2-copy">
          <p className="login-v2-eyebrow"><i /> PRIVATE ADMINISTRATION <span>/ DISCORD OAUTH2</span></p>
          <h1>One place.<br /><span>Every server.</span></h1>
          <p className="login-v2-description">
            Configure Lemegeton, manage command access and inspect the systems behind your Discord servers.
          </p>

          {cancelled ? <div className="login-v2-notice" role="status">Sign-in was cancelled. Nothing has been changed.</div> : null}

          <form className="login-v2-form" action="/oauth/start" method="post">
            <button
              className="button primary login-v2-submit"
              type="submit"
              aria-describedby="login-policy-agreement"
            >
              <img src="/brand/discord.svg" alt="" aria-hidden="true" width={17} height={17} />
              <span>Continue with Discord</span>
              <Icon name="arrow-up-right" size={16} />
            </button>
          </form>

          <div className="login-v2-agreement" id="login-policy-agreement" role="note" aria-label="Sign-in agreement">
            <Icon name="shield-check" size={15} />
            <p>
              By selecting <strong>Continue with Discord</strong>, you confirm that you have read and agree to the{" "}
              <a href="/terms-of-service" target="_blank" rel="noopener noreferrer">Terms of Service</a>,{" "}
              <a href="/privacy-policy" target="_blank" rel="noopener noreferrer">Privacy Policy</a>, and{" "}
              <a href="/community-guidelines" target="_blank" rel="noopener noreferrer">Community Guidelines</a>.
            </p>
          </div>

          <nav className="login-v2-policy" aria-label="Additional legal information">
            {POLICIES.map((policy, index) => (
              <span key={policy.label}>
                {index > 0 ? <span aria-hidden="true"> · </span> : null}
                <a href={policy.href} target="_blank" rel="noopener noreferrer">{policy.label}</a>
              </span>
            ))}
          </nav>

          <div className="login-v2-assurances">
            <span><b>01</b> Discord permissions checked server-side</span>
            <span><b>02</b> Configuration isolated by server</span>
            <span><b>03</b> Credentials remain private</span>
          </div>
        </div>

        <div className="login-v2-visual" aria-hidden="true">
          <div className="login-v2-visual-grid" />
          <SceneLoader />
          <div className="login-v2-visual-caption"><span>FIG. 01</span><span>LEMEGETON / SYSTEM GEOMETRY</span></div>
        </div>
      </section>

      <footer className="login-v2-footer">
        <span>LEMEGETON / CONTROL PLANE</span>
        <span><a href="/how-it-works">HOW IT WORKS</a> <span aria-hidden="true">·</span> <a href="/status">SYSTEM STATUS</a> <span aria-hidden="true">·</span> <a href="/issues" target="_blank" rel="noreferrer">REPORT AN ISSUE</a> <span aria-hidden="true">·</span> AUTHORIZED ACCESS ONLY</span>
      </footer>
    </main>
  );
}
