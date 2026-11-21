import type { JSX } from "react";

export function PickerMarkup(): JSX.Element {
  return (
    <main className="picker-shell">
      <header className="picker-topbar">
        <div className="brand-lockup" role="group" aria-label="Lemegeton role studio">
          <span className="brand-mark" aria-hidden="true">
            {"L."}
          </span>
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
          {"Make it"}
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
      <section id="loading" className="card" aria-live="polite">
        {"Loading your role…"}
      </section>
      <section id="problem" className="card hidden" role="alert">
        <h2 id="problem-title">
        </h2>
        <p id="problem-text">
        </p>
      </section>
      <div id="app" className="hidden">
        <section className="card" aria-labelledby="preview-title">
          <h2 id="preview-title">
            {"Preview"}
          </h2>
          <div className="preview-grid">
            <div className="msg msg-dark" aria-label="Dark theme preview" role="group">
              <img className="avatar" data-avatar="" alt="" referrerPolicy="no-referrer" />
              <div className="msg-body">
                <div className="name-line">
                  <span className="name" data-name="">
                  </span>
                  <img className="role-icon hidden" data-icon-img="" alt="Role icon" referrerPolicy="no-referrer" />
                  <span className="role-icon-emoji hidden" data-icon-emoji="">
                  </span>
                  <span className="time" data-time="">
                  </span>
                </div>
                <div className="msg-text">
                  {"Hey! This is how my name looks."}
                </div>
              </div>
            </div>
            <div className="msg msg-light" aria-label="Light theme preview" role="group">
              <img className="avatar" data-avatar="" alt="" referrerPolicy="no-referrer" />
              <div className="msg-body">
                <div className="name-line">
                  <span className="name" data-name="">
                  </span>
                  <img className="role-icon hidden" data-icon-img="" alt="Role icon" referrerPolicy="no-referrer" />
                  <span className="role-icon-emoji hidden" data-icon-emoji="">
                  </span>
                  <span className="time" data-time="">
                  </span>
                </div>
                <div className="msg-text">
                  {"Hey! This is how my name looks."}
                </div>
              </div>
            </div>
          </div>
          <div className="chip-line">
            <span className="muted">
              {"Role"}
            </span>
            <span className="chip">
              <span className="dot" id="chip-dot">
              </span>
              <span className="chip-name" id="chip-name">
              </span>
            </span>
          </div>
          <p id="contrast-note" className="status-note hidden">
          </p>
          <div className="toolbar">
            <button id="reset" className="btn btn-secondary" type="button" disabled={true}>
              {"Reset to saved"}
            </button>
            <span id="dirty-note" className="hint">
              {"No unsaved changes."}
            </span>
          </div>
          <p className="hint">
            {"This link closes"}
            <span id="expires">
            </span>
            {"without use (saving or reloading counts as use), and"}
            <span id="expires-max">
            </span>
            {"at the latest. Don't share it: anyone with it can change your role."}
          </p>
          <p id="cooldown-note" className="hint hidden">
          </p>
        </section>
        <section className="card">
          <div className="tabs" role="tablist" aria-label="What to change">
            <button className="tab" type="button" role="tab" id="tab-color" aria-controls="panel-color" aria-selected="true">
              {"Color"}
            </button>
            <button className="tab" type="button" role="tab" id="tab-icon" aria-controls="panel-icon" aria-selected="false" tabIndex="-1">
              {"Role Icon"}
            </button>
            <button className="tab" type="button" role="tab" id="tab-name" aria-controls="panel-name" aria-selected="false" tabIndex="-1">
              {"Name"}
            </button>
          </div>
          <div id="panel-color" role="tabpanel" aria-labelledby="tab-color" tabIndex="0">
            <fieldset className="segmented">
              <legend>
                {"Style"}
              </legend>
              <div className="segments">
                <input type="radio" name="mode" id="mode-solid" value="solid" aria-describedby="mode-hint" />
                <label htmlFor="mode-solid">
                  {"Solid"}
                </label>
                <input type="radio" name="mode" id="mode-gradient" value="gradient" aria-describedby="mode-hint" />
                <label htmlFor="mode-gradient">
                  {"Gradient"}
                </label>
                <input type="radio" name="mode" id="mode-holographic" value="holographic" aria-describedby="mode-hint" />
                <label htmlFor="mode-holographic">
                  {"Holographic"}
                </label>
              </div>
            </fieldset>
            <p id="mode-hint" className="hint hidden">
              {"Gradient and Holographic need 3 server boosts (Discord's Enhanced Role Styles), which this server doesn't have yet."}
            </p>
            <div id="panel-solid" className="mode-panel">
              <div className="field" data-color-field="primary" data-label="Color">
              </div>
              <button id="set-solid" className="btn btn-primary" type="button" data-set="solid">
                {"Set color"}
              </button>
              <p id="status-solid" className="status" role="status">
              </p>
            </div>
            <div id="panel-gradient" className="mode-panel hidden">
              <div id="gradient-bar" className="gradient-bar" aria-hidden="true">
              </div>
              <div className="field" data-color-field="primary" data-label="Primary">
              </div>
              <div className="field" data-color-field="secondary" data-label="Secondary">
              </div>
              <button id="set-gradient" className="btn btn-primary" type="button" data-set="gradient">
                {"Set gradient"}
              </button>
              <p id="status-gradient" className="status" role="status">
              </p>
            </div>
            <div id="panel-holographic" className="mode-panel hidden">
              <div className="gradient-bar holo-fill" aria-hidden="true">
              </div>
              <p>
                {"Discord's holographic style uses fixed colors, so there's nothing to pick."}
              </p>
              <button id="set-holographic" className="btn btn-primary" type="button" data-set="holographic">
                {"Set holographic"}
              </button>
              <p id="status-holographic" className="status" role="status">
              </p>
            </div>
            <div id="palette" className="mode-panel">
              <h2>
                {"Colors extracted from your profile picture"}
              </h2>
              <p id="palette-status" className="hint">
                {"Loading colors…"}
              </p>
              <fieldset className="palette-group hidden" id="palette-primary">
                <legend id="palette-primary-legend">
                  {"Primary"}
                </legend>
                <div className="swatches">
                </div>
              </fieldset>
              <fieldset className="palette-group hidden" id="palette-secondary">
                <legend>
                  {"Secondary"}
                </legend>
                <div className="swatches">
                </div>
              </fieldset>
            </div>
          </div>
          <div id="panel-icon" role="tabpanel" aria-labelledby="tab-icon" tabIndex="0" className="hidden">
            <p>
              {"Current icon:"}
              <span id="icon-current">
              </span>
            </p>
            <p id="icon-unavailable" className="hint hidden">
              {"Role icons need Boost Level 2 (Discord's Role Icons perk), and this server doesn't have it yet."}
            </p>
            <div id="icon-tools">
              <fieldset className="segmented">
                <legend>
                  {"Icon from"}
                </legend>
                <div className="segments">
                  <input type="radio" name="icon-source" id="source-upload" value="upload" defaultChecked={true} />
                  <label htmlFor="source-upload">
                    {"Upload"}
                  </label>
                  <input type="radio" name="icon-source" id="source-link" value="link" />
                  <label htmlFor="source-link">
                    {"Link"}
                  </label>
                  <input type="radio" name="icon-source" id="source-emoji" value="emoji" />
                  <label htmlFor="source-emoji">
                    {"Emoji"}
                  </label>
                </div>
              </fieldset>
              <div id="icon-upload" className="mode-panel">
                <input id="icon-file" className="visually-hidden" type="file" accept="image/png,image/jpeg" aria-describedby="dropzone-hint" />
                <label id="dropzone" className="dropzone" htmlFor="icon-file">
                  <span>
                    {"Drop an image here, or click to browse"}
                  </span>
                  <span id="dropzone-hint" className="hint">
                    {"PNG or JPEG · up to"}
                    <span data-source-max="">
                    </span>
                  </span>
                </label>
              </div>
              <div id="icon-link" className="mode-panel hidden">
                <div className="field">
                  <label htmlFor="icon-url">
                    {"Image link"}
                  </label>
                  <div className="color-row">
                    <input id="icon-url" className="text-input url-input" type="url" inputMode="url" autoComplete="off" spellCheck="false" placeholder="https://…" aria-describedby="icon-url-help" />
                    <button id="icon-load" className="btn btn-secondary" type="button" data-icon-action="">
                      {"Load"}
                    </button>
                  </div>
                  <p id="icon-url-help" className="hint">
                    {"A direct link to a PNG or JPEG, up to"}
                    <span data-source-max="">
                    </span>
                    {". Links that redirect won't work, so paste the image's own address."}
                  </p>
                </div>
              </div>
              <div id="icon-emoji" className="mode-panel hidden">
                <div className="field">
                  <label htmlFor="emoji-input">
                    {"Emoji"}
                  </label>
                  <input id="emoji-input" className="text-input emoji-input" type="text" maxLength="16" autoComplete="off" spellCheck="false" aria-describedby="emoji-help" />
                  <p id="emoji-help" className="hint">
                    {"Type or paste one standard Unicode emoji. Custom server emoji can't be role icons."}
                  </p>
                </div>
              </div>
              <p id="icon-load-status" className="status" role="status">
              </p>
              <div id="crop" className="mode-panel hidden">
                <h2>
                  {"Crop"}
                </h2>
                <div className="crop-row">
                  <div id="crop-stage" className="crop-stage" tabIndex="0" role="group" aria-label="Crop area" aria-describedby="crop-help">
                    <img id="crop-img" alt="" draggable="false" />
                  </div>
                  <div className="crop-side">
                    <img id="crop-preview" className="crop-preview" alt="Your icon as it will look" />
                    <p className="hint">
                      {"Preview"}
                    </p>
                  </div>
                </div>
                <div className="field">
                  <label htmlFor="crop-zoom">
                    {"Zoom"}
                  </label>
                  <input id="crop-zoom" className="zoom" type="range" min="1" max="10" step="0.01" value="1" />
                </div>
                <p id="crop-help" className="hint">
                  {"Drag the image, or use the arrow keys (hold Shift for bigger steps). Press + or − to zoom."}
                </p>
              </div>
            </div>
            <div className="toolbar">
              <button id="set-icon" className="btn btn-primary" type="button" data-icon-action="">
                {"Set icon"}
              </button>
              <button id="edit-crop" className="btn btn-secondary" type="button" data-icon-action="">
                {"Edit current crop"}
              </button>
              <button id="remove-icon" className="btn btn-secondary" type="button" data-icon-action="">
                {"Remove current icon"}
              </button>
            </div>
            <p id="status-icon" className="status" role="status">
            </p>
          </div>
          <div id="panel-name" role="tabpanel" aria-labelledby="tab-name" tabIndex="0" className="hidden">
            <div className="field">
              <label htmlFor="name-input">
                {"Role name"}
              </label>
              <input id="name-input" className="text-input name-input" type="text" autoComplete="off" spellCheck="false" aria-describedby="name-count name-error" />
              <p id="name-count" className="hint">
              </p>
              <p id="name-error" className="field-error hidden">
              </p>
            </div>
            <button id="set-name" className="btn btn-primary" type="button" data-set="name">
              {"Set name"}
            </button>
            <p id="status-name" className="status" role="status">
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}
