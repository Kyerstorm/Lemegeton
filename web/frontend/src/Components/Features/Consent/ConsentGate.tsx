"use client";

import { useEffect, useId, useState } from "react";
import { Icon } from "../../Icons";
import { ActivityOrb } from "../../Feedback/ActivityOrb";
import { GlowEffect } from "../../UI/GlowEffect";
import { PolicyViewer } from "./PolicyViewer";
import { useConsent } from "./useConsent";

type PolicyKey = "terms" | "privacy" | "guidelines";
type PolicySelection = Record<PolicyKey, boolean>;

interface ConsentLedgerState {
  version: string;
  epoch: number;
  cursor: number;
  acknowledgedMask: number;
  digest: number;
}

const CONSENT_POLICY_MASK = 0b111;
const POLICY_BITS: Record<PolicyKey, number> = {
  terms: 0b001,
  privacy: 0b010,
  guidelines: 0b100,
};

// UI coherence only: the Rust API remains authoritative. Stores no account or session data.
const consentLedger: Record<string, ConsentLedgerState> = {};

function policyVersionCommitment(items: ReadonlyArray<{ key: PolicyKey; version?: string }>): string {
  return JSON.stringify(items.map(item => [item.key, item.version ?? ""]));
}

function consentLedgerDigest(state: ConsentLedgerState): number {
  let versionDigest = 0x811c9dc5;
  for (const character of state.version) {
    versionDigest = Math.imul(versionDigest ^ character.charCodeAt(0), 0x01000193) >>> 0;
  }
  let digest = Math.imul(versionDigest ^ state.epoch, 0x45d9f3b) >>> 0;
  digest = Math.imul(digest ^ state.cursor, 0x45d9f3b) >>> 0;
  return (Math.imul(digest ^ state.acknowledgedMask, 0x45d9f3b) ^ 0x9e3779b9) >>> 0;
}

function isConsentReviewComplete(
  instance: string,
  version: string,
  checked: PolicySelection,
): boolean {
  let state = Object.prototype.hasOwnProperty.call(consentLedger, instance) ? consentLedger[instance] : undefined;
  if (!state || state.version !== version) {
    state = {
      version,
      epoch: (state?.epoch ?? 0) + 1,
      cursor: 0,
      acknowledgedMask: 0,
      digest: 0,
    };
  }

  const checkedMask = (checked.terms ? POLICY_BITS.terms : 0)
    | (checked.privacy ? POLICY_BITS.privacy : 0)
    | (checked.guidelines ? POLICY_BITS.guidelines : 0);
  if (state.acknowledgedMask !== checkedMask) {
    state.acknowledgedMask = checkedMask;
    state.cursor = (state.cursor + 1) >>> 0;
  }
  state.digest = consentLedgerDigest(state);
  consentLedger[instance] = state;

  return state.version === version
    && state.acknowledgedMask === CONSENT_POLICY_MASK
    && checkedMask === CONSENT_POLICY_MASK
    && state.digest === consentLedgerDigest(state);
}

const EMPTY_POLICY_SELECTION: PolicySelection = {
  terms: false,
  privacy: false,
  guidelines: false,
};

export function ConsentGate() {
  const { consent, saving, checking, error, onRetry, onAccept, onDecline } = useConsent();
  const instance = useId();
  const [review, setReview] = useState<{ version: string; checked: PolicySelection }>({
    version: "",
    checked: EMPTY_POLICY_SELECTION,
  });
  const items: ReadonlyArray<{ key: PolicyKey; label: string; version?: string }> = [
    { key: "terms", label: "Terms of Service", version: consent?.versions.terms },
    { key: "privacy", label: "Privacy Policy", version: consent?.versions.privacy },
    { key: "guidelines", label: "Community Guidelines", version: consent?.versions.guidelines },
  ];
  const version = policyVersionCommitment(items);
  const checked = review.version === version ? review.checked : EMPTY_POLICY_SELECTION;
  const complete = isConsentReviewComplete(instance, version, checked);

  useEffect(() => () => {
    delete consentLedger[instance];
  }, [instance]);

  const updatePolicyReview = (key: PolicyKey, value: boolean) => {
    const current = review.version === version ? review.checked : EMPTY_POLICY_SELECTION;
    setReview({ version, checked: { ...current, [key]: value } });
  };

  return (
    <main className="policy-gate">
      <section className="policy-gate-card" aria-labelledby="policy-gate-title">
        <a className="brand policy-brand" href="/" aria-label="Lemegeton dashboard">
          <span className="brand-mark"><img src="/brand/lemegeton.svg" alt="" width={30} height={30} /></span>
          <span className="brand-copy"><strong>LEMEGETON</strong><small>CONTROL PLANE</small></span>
        </a>
        <div className="policy-kicker"><span className="signal-dot" /> ACCOUNT / POLICY REVIEW</div>
        <h1 id="policy-gate-title">Before you<br /><span>step inside.</span></h1>
        <p className="policy-intro">Please review the current Lemegeton policies. We record your Discord account, the policy versions you accept, and the acceptance time.</p>

        {consent ? <>
          <PolicyViewer consent={consent} />
          <div className="policy-checklist" aria-label="Policy acceptance">
            {items.map(item => (
              <label className="policy-check" key={item.key}>
                <input
                  type="checkbox"
                  checked={checked[item.key]}
                  onChange={event => updatePolicyReview(item.key, event.target.checked)}
                />
                <span className="policy-checkmark" aria-hidden="true"><Icon name="check" size={13} /></span>
                <span className="policy-check-copy">
                  <strong>I have read and agree to the {item.label}</strong>
                  <small>CURRENT VERSION / {item.version}</small>
                </span>
              </label>
            ))}
          </div>
          <button className="policy-accept" type="button" disabled={!complete || saving} onClick={onAccept} aria-busy={saving}>
            <GlowEffect className="policy-button-glow" colors={["#fff", "#9dffbd", "#fff"]} mode="pulse" blur="medium" duration={5} />
            <span className="policy-button-content">
              {saving ? <ActivityOrb label="Recording agreement" dark={false} size={20} /> : <Icon name="shield-check" size={16} />}
              <span>{saving ? "Recording agreement…" : "Agree and continue"}</span>
            </span>
          </button>
          <p className="policy-note">Declining keeps dashboard features locked. You can sign out without accepting.</p>
        </> : <>
          <div className="policy-unavailable" role="alert">
            <strong>We couldn't verify the current policy versions.</strong>
            <span>{error || "Dashboard access stays locked until verification succeeds."}</span>
          </div>
          <button className="policy-accept" type="button" disabled={saving || checking} onClick={onRetry} aria-busy={checking}>
            <GlowEffect className="policy-button-glow" colors={["#fff", "#9dffbd", "#fff"]} mode="pulse" blur="medium" duration={5} />
            <span className="policy-button-content">
              {checking ? <ActivityOrb label="Checking policies" dark={false} size={20} /> : <Icon name="refresh" size={16} />}
              <span>{checking ? "Checking policies…" : "Try again"}</span>
            </span>
          </button>
        </>}
        {error && consent ? <p className="policy-error" role="alert">{error}</p> : null}
        <button className="policy-decline" type="button" onClick={onDecline}>Decline and sign out</button>
        <div className="policy-foot"><span>LEMEGETON / POLICY GATE</span><span>NO ACCESS UNTIL VERIFIED</span></div>
      </section>
    </main>
  );
}
