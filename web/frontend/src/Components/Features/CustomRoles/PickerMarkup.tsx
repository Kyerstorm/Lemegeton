import type { JSX } from "react";
import { RolePreview } from "./RolePreview";
import { ColorPicker } from "./ColorPicker";
import { RoleIconEditor } from "./RoleIconEditor";
import { RoleNameEditor } from "./RoleNameEditor";

export function PickerMarkup(): JSX.Element {
  return (
    <main className="picker-shell">
      <header className="picker-topbar">
        <div className="brand-lockup" role="group" aria-label="Lemegeton role studio">
          <span className="brand-mark" aria-hidden="true">
            {"L."}
          </span>
          {" "}
          <span className="brand-copy">
            <strong>
              {"LEMEGETON"}
            </strong>
            <small>
              {"COMMUNITY CONTROL"}
            </small>
          </span>
        </div>
        <div className="topbar-status" aria-label="Private role editing link">
          <span className="status-led" aria-hidden="true">
          </span>
          {" "}
          <span>
            <strong>
              {"PRIVATE SESSION"}
            </strong>
            <small>
              {"SECURE ROLE ACCESS"}
            </small>
          </span>
        </div>
      </header>
      <section className="picker-hero" aria-labelledby="picker-title">
        <p className="eyebrow">
          <span>
            {"ROLE STUDIO"}
          </span>
          <span className="eyebrow-divider">
            {"/"}
          </span>
          <span>
            {"PERSONALIZATION"}
          </span>
        </p>
        <h1 id="picker-title">
          {"Make it "}
          <span>
            {"yours."}
          </span>
        </h1>
        <p className="lede">
          {"Tune your role’s color, name, and icon. Changes are checked by the bot and applied to your Discord role."}
        </p>
      </section>
      <div id="banner-access" className="banner banner-error hidden" role="alert">
        <strong id="banner-access-title">
        </strong>
        <p id="banner-access-text">
        </p>
      </div>
      <div id="banner-debug" className="banner banner-warning hidden">
        <strong>
          {"Test switch on"}
        </strong>
        <p>
          {"Gradient and Holographic are unlocked so you can preview them. This server doesn't have Discord's Enhanced Role Styles (3 server boosts), so saving them will be refused."}
        </p>
      </div>
      <div id="banner-debug-icons" className="banner banner-warning hidden">
        <strong>
          {"Test switch on"}
        </strong>
        <p>
          {"The Role Icon tab is unlocked so you can test it. This server doesn't have Discord's Role Icons (Boost Level 2), so setting an icon will be refused after your image or emoji is checked."}
        </p>
      </div>
      <section id="loading" className="card picker-loading" role="status" aria-live="polite" aria-label="Loading role studio">
        <div className="picker-loading-previews" aria-hidden="true">
          <div className="picker-loading-preview">
            <span className="picker-skeleton picker-skeleton-avatar" />
            <span className="picker-loading-copy">
              <span className="picker-skeleton picker-skeleton-name" />
              <span className="picker-skeleton picker-skeleton-caption" />
            </span>
          </div>
          <div className="picker-loading-preview">
            <span className="picker-skeleton picker-skeleton-avatar" />
            <span className="picker-loading-copy">
              <span className="picker-skeleton picker-skeleton-name" />
              <span className="picker-skeleton picker-skeleton-caption" />
            </span>
          </div>
        </div>
        <div className="picker-loading-tabs" aria-hidden="true">
          <span className="picker-skeleton picker-skeleton-tab" />
          <span className="picker-skeleton picker-skeleton-tab" />
          <span className="picker-skeleton picker-skeleton-tab" />
        </div>
        <div className="picker-loading-field" aria-hidden="true">
          <span className="picker-skeleton picker-skeleton-label" />
          <span className="picker-skeleton picker-skeleton-control" />
        </div>
        <div className="picker-loading-field" aria-hidden="true">
          <span className="picker-skeleton picker-skeleton-label" />
          <span className="picker-skeleton picker-skeleton-control" />
        </div>
        <span className="visually-hidden">Loading your role settings.</span>
      </section>
      <section id="problem" className="card hidden" role="alert">
        <h2 id="problem-title">
        </h2>
        <p id="problem-text">
        </p>
      </section>
      <div id="app" className="hidden">
        <RolePreview />

        <section className="card">
          <div className="tabs" role="tablist" aria-label="What to change">
            <button className="tab" type="button" role="tab" id="tab-color" aria-controls="panel-color" aria-selected="true">
              {"Color"}
            </button>
            {" "}
            <button className="tab" type="button" role="tab" id="tab-icon" aria-controls="panel-icon" aria-selected="false" tabIndex={-1}>
              {"Role Icon"}
            </button>
            {" "}
            <button className="tab" type="button" role="tab" id="tab-name" aria-controls="panel-name" aria-selected="false" tabIndex={-1}>
              {"Name"}
            </button>
          </div>
          <ColorPicker />
          <RoleIconEditor />
          <RoleNameEditor />
        </section>
      </div>
    </main>
  );
}
