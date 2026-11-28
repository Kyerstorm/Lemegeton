import { ImageUploader } from "./ImageUploader";
import { ImageCropper } from "./ImageCropper";
import type { JSX } from "react";

export function RoleIconEditor(): JSX.Element {
  return (
    <div id="panel-icon" role="tabpanel" aria-labelledby="tab-icon" tabIndex={0} className="hidden">
                <p>
                  {"Current icon: "}
                  <span id="icon-current">
                  </span>
                </p>
                <p id="icon-unavailable" className="hint hidden">
                  {"Role icons need Boost Level 2 (Discord's Role Icons perk), and this server doesn't have it yet."}
                </p>
                <div id="icon-tools">
                  <ImageUploader />
                  <ImageCropper />
                </div>
                <div className="toolbar">
                  <button id="set-icon" className="btn btn-primary" type="button" data-icon-action="">
                    {"Set icon"}
                  </button>
                  {" "}
                  <button id="edit-crop" className="btn btn-secondary" type="button" data-icon-action="">
                    {"Edit current crop"}
                  </button>
                  {" "}
                  <button id="remove-icon" className="btn btn-secondary" type="button" data-icon-action="">
                    {"Remove current icon"}
                  </button>
                </div>
                <p id="status-icon" className="status" role="status">
                </p>
              </div>
  );
}
