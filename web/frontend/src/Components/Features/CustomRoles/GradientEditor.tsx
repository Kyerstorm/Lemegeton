import type { JSX } from "react";

export function GradientEditor(): JSX.Element {
  return (
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
  );
}
