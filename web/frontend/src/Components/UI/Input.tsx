import { useId, type InputHTMLAttributes, type ReactNode } from "react";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  leading?: ReactNode;
  wrapperClassName?: string;
}

export function Input({ id, label, hint, leading, wrapperClassName, ...props }: InputProps) {
  const labelId = useId();
  const hintId = useId();
  const labelledBy = [props["aria-labelledby"], label ? labelId : undefined]
    .filter(Boolean)
    .join(" ") || undefined;
  const describedBy = [props["aria-describedby"], hint ? hintId : undefined]
    .filter(Boolean)
    .join(" ") || undefined;

  return (
    <label className={["form-control", wrapperClassName].filter(Boolean).join(" ")} htmlFor={id}>
      {label ? <span id={labelId} className="form-control-label">{label}</span> : null}
      {leading}
      <input id={id} {...props} aria-labelledby={labelledBy} aria-describedby={describedBy} />
      {hint ? <small id={hintId} className="form-control-hint">{hint}</small> : null}
    </label>
  );
}
