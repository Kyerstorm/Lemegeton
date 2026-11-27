import type { KeyboardEvent } from "react";

export interface TabOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export function Tabs({ value, options, onChange, label }: {
  value: string;
  options: readonly TabOption[];
  onChange: (value: string) => void;
  label: string;
}) {
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const isArrow = event.key === "ArrowLeft" || event.key === "ArrowRight";
    if (!isArrow && event.key !== "Home" && event.key !== "End") return;

    const enabledTabs = Array.from(
      event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]:not(:disabled)'),
    );
    if (!enabledTabs.length) return;

    event.preventDefault();
    const focusedIndex = enabledTabs.indexOf(event.target as HTMLButtonElement);
    const selectedIndex = enabledTabs.findIndex(tab => tab.dataset.value === value);
    const index = focusedIndex >= 0 ? focusedIndex : Math.max(0, selectedIndex);
    const nextIndex = event.key === "Home"
      ? 0
      : event.key === "End"
        ? enabledTabs.length - 1
        : (index + (event.key === "ArrowRight" ? 1 : enabledTabs.length - 1)) % enabledTabs.length;
    const nextTab = enabledTabs[nextIndex];
    if (!nextTab) return;

    nextTab.focus();
    onChange(nextTab.dataset.value ?? value);
  };

  return (
    <div className="ui-tabs" role="tablist" aria-label={label} aria-orientation="horizontal" onKeyDown={onKeyDown}>
      {options.map(option => (
        <button
          key={option.value}
          type="button"
          role="tab"
          aria-selected={value === option.value}
          data-value={option.value}
          tabIndex={value === option.value ? 0 : -1}
          disabled={option.disabled}
          className={"ui-tab" + (value === option.value ? " active" : "")}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
