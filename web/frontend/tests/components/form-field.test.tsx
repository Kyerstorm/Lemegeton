import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FormField } from "../../src/Components/Forms/FormField";

describe("FormField", () => {
  it("associates hint text with its form control", () => {
    render(
      <FormField label="Server language" htmlFor="server-language" hint="Choose the language used by server messages.">
        <select id="server-language" defaultValue="en">
          <option value="en">English</option>
        </select>
      </FormField>,
    );

    const control = screen.getByLabelText("Server language");
    const descriptionId = control.getAttribute("aria-describedby");
    expect(descriptionId).toBeTruthy();
    expect(document.getElementById(descriptionId!)?.textContent).toBe(
      "Choose the language used by server messages.",
    );
    expect(control.getAttribute("aria-invalid")).toBeNull();
  });

  it("marks invalid controls and announces the associated error", () => {
    render(
      <FormField label="Contribution channel" htmlFor="upload-channel" error="Choose a channel you can manage.">
        <select id="upload-channel" defaultValue="">
          <option value="">Not configured</option>
          <option value="123">#archive</option>
        </select>
      </FormField>,
    );

    const control = screen.getByLabelText("Contribution channel");
    const descriptionId = control.getAttribute("aria-describedby");
    const error = document.getElementById(descriptionId!);

    expect(control.getAttribute("aria-invalid")).toBe("true");
    expect(error?.getAttribute("role")).toBe("alert");
    expect(error?.textContent).toBe("Choose a channel you can manage.");
  });
});
