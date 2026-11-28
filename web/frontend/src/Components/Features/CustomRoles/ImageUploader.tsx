import type { JSX } from "react";

export function ImageUploader(): JSX.Element {
  return (
    <div className="image-uploader">
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
                      {" "}
                      <span id="dropzone-hint" className="hint">
                        {"PNG or JPEG · up to "}
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
                        {"A direct link to a PNG or JPEG, up to "}
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
                      <input id="emoji-input" className="text-input emoji-input" type="text" maxLength={16} autoComplete="off" spellCheck="false" aria-describedby="emoji-help" />
                      <p id="emoji-help" className="hint">
                        {"Type or paste one standard Unicode emoji. Custom server emoji can't be role icons."}
                      </p>
                    </div>
                  </div>
                  <p id="icon-load-status" className="status" role="status">
                  </p>
    </div>
  );
}
