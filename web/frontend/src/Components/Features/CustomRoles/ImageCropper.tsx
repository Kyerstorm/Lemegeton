import type { JSX } from "react";

export function ImageCropper(): JSX.Element {
  return (
    <div id="crop" className="mode-panel hidden">
                    <h2>
                      {"Crop"}
                    </h2>
                    <div className="crop-row">
                      <div id="crop-stage" className="crop-stage" tabIndex={0} role="group" aria-label="Crop area" aria-describedby="crop-help">
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
                      <input id="crop-zoom" className="zoom" type="range" min="1" max="10" step="0.01" defaultValue={1} />
                    </div>
                    <p id="crop-help" className="hint">
                      {"Drag the image, or use the arrow keys (hold Shift for bigger steps). Press + or − to zoom."}
                    </p>
                  </div>
  );
}
