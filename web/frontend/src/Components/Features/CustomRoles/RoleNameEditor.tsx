import type { JSX } from "react";

export function RoleNameEditor(): JSX.Element {
  return (
    <div id="panel-name" role="tabpanel" aria-labelledby="tab-name" tabIndex={0} className="hidden">
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
  );
}
