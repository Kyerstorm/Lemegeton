import { GradientEditor } from "./GradientEditor";
import type { JSX } from "react";

export function ColorPicker(): JSX.Element {
  return (
    <div id="panel-color" role="tabpanel" aria-labelledby="tab-color" tabIndex={0}>
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
                <GradientEditor />
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
                  <p id="palette-status" className="hint" aria-live="polite">
                    {"Extracting colors from your profile picture…"}
                  </p>
                  <div id="palette-loading" className="palette-loading" role="status" aria-label="Extracting profile picture colors">
                    {Array.from({ length: 6 }, (_, index) => <span className="picker-skeleton picker-skeleton-swatch" key={index} />)}
                  </div>
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
  );
}
