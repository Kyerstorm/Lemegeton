import type { JSX } from "react";

export function RolePreview(): JSX.Element {
  return (
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
                      {" "}
                      <img className="role-icon hidden" data-icon-img="" alt="Role icon" referrerPolicy="no-referrer" />
                      <span className="role-icon-emoji hidden" data-icon-emoji="">
                      </span>
                      {" "}
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
                      {" "}
                      <img className="role-icon hidden" data-icon-img="" alt="Role icon" referrerPolicy="no-referrer" />
                      <span className="role-icon-emoji hidden" data-icon-emoji="">
                      </span>
                      {" "}
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
                {" "}
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
                {" "}
                <span id="dirty-note" className="hint">
                  {"No unsaved changes."}
                </span>
              </div>
              <p className="hint">
                {"This link closes "}
                <span id="expires">
                </span>
                {" without use (saving or reloading counts as use), and "}
                <span id="expires-max">
                </span>
                {" at the latest. Don't share it: anyone with it can change your role."}
              </p>
              <p id="cooldown-note" className="hint hidden">
              </p>
            </section>
  );
}
