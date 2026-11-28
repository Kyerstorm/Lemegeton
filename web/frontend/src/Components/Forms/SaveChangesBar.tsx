import { Icon } from "../Icons";
import { ActivityOrb } from "../Feedback/ActivityOrb";
import { GlowEffect } from "../UI/GlowEffect";

export interface SaveChangesBarProps {
  variant?: "sticky" | "inline";
  label: string;
  detail?: string;
  ariaLabel: string;
  saving?: boolean;
  saveDisabled?: boolean;
  resetDisabled?: boolean;
  saveLabel?: string;
  savingLabel?: string;
  onReset: () => void;
  onSave: () => void;
}

export function SaveChangesBar({
  variant = "sticky", label, detail, ariaLabel, saving = false, saveDisabled = false,
  resetDisabled = false, saveLabel = "Save Changes", savingLabel = "Saving…", onReset, onSave,
}: SaveChangesBarProps) {
  return (
    <div className={variant === "sticky" ? "command-savebar" : "access-footer"} role="region" aria-label={ariaLabel}>
      <span className="save-changes-copy">
        {variant === "sticky" ? <strong>{label}</strong> : label}
        {detail ? <small>{detail}</small> : null}
      </span>
      <div>
        <button type="button" className="command-reset" onClick={onReset} disabled={resetDisabled || saving}><Icon name="reset" size={14} />Reset</button>
        <button type="button" className="command-save" onClick={onSave} disabled={saveDisabled || saving} aria-busy={saving} aria-label={saving ? savingLabel : saveLabel}>
          <GlowEffect className="command-save-glow" colors={["#fff", "#777", "#fff"]} mode="rotate" blur="medium" duration={8} scale={1.08} />
          <span className="save-button-content">
            {saving ? <ActivityOrb label={savingLabel} size={20} /> : <Icon name="save" size={14} />}
            <span>{saving ? savingLabel : saveLabel}</span>
          </span>
        </button>
      </div>
    </div>
  );
}
