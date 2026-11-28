import { useId, type SelectHTMLAttributes } from "react";

export interface FormOption {
  value: string;
  label: string;
}

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  hint?: string;
  options: readonly FormOption[];
  wrapperClassName?: string;
}

export function Select({ id, label, hint, options, wrapperClassName, ...props }: SelectProps) {
  const labelId = useId();
  const hintId = useId();
  const labelledBy = [props["aria-labelledby"], labelId].filter(Boolean).join(" ");
  const describedBy = [props["aria-describedby"], hint ? hintId : undefined]
    .filter(Boolean)
    .join(" ") || undefined;

  return (
    <label className={["form-control", wrapperClassName].filter(Boolean).join(" ")} htmlFor={id}>
      <span id={labelId} className="form-control-label">{label}</span>
      <select id={id} {...props} aria-labelledby={labelledBy} aria-describedby={describedBy}>
        {options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
      {hint ? <small id={hintId} className="form-control-hint">{hint}</small> : null}
    </label>
  );
}

export interface MultiSelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "multiple"> {
  options: readonly FormOption[];
}

export function MultiSelect({ id, options, ...props }: MultiSelectProps) {
  return (
    <select id={id} multiple {...props}>
      {options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
    </select>
  );
}
