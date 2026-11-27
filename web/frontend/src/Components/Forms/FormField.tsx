import { cloneElement, isValidElement, useId, type ReactNode } from "react";

export interface FormFieldProps {
  label: string;
  htmlFor?: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}

type AccessibleControlProps = {
  "aria-describedby"?: string;
  "aria-invalid"?: boolean;
};

export function FormField({ label, htmlFor, hint, error, children }: FormFieldProps) {
  const descriptionId = useId();
  const description = error || hint;
  const control = isValidElement<AccessibleControlProps>(children)
    ? cloneElement(children, {
      "aria-describedby": [
        children.props["aria-describedby"],
        description ? descriptionId : undefined,
      ].filter(Boolean).join(" ") || undefined,
      "aria-invalid": error ? true : children.props["aria-invalid"],
    })
    : children;

  return (
    <div className="form-field">
      <label className="form-control-label" htmlFor={htmlFor}>{label}</label>
      {control}
      {description ? (
        <small
          id={descriptionId}
          className={error ? "form-field-error" : "form-control-hint"}
          role={error ? "alert" : undefined}
        >
          {description}
        </small>
      ) : null}
    </div>
  );
}
