import type { Dispatch, SetStateAction } from "react";
import { useDialogFocus } from "../../Hooks/useDialogFocus";
import { Icon } from "../../Icons";
import { Skeleton } from "../../Feedback/LoadingState";
import { SaveChangesBar } from "../../Forms/SaveChangesBar";
import { SectionError } from "../../Feedback/SectionError";
import type { CommandAccessPolicy, CommandAccessResponse } from "../../../Types/dashboard";
import { RoleAccessRules } from "./RoleAccessRules";
import { ChannelAccessRules } from "./ChannelAccessRules";
import { AccessPreview } from "./AccessPreview";

export function CommandAccessEditor({ target, loading, error, errorStatus, options, draft, dirty, saving, onRetry, setDraft, onClose, onReset, onSave }: {
  target: string;
  loading: boolean;
  error: string;
  errorStatus: number | null;
  options: CommandAccessResponse | null;
  draft: CommandAccessPolicy | null;
  dirty: boolean;
  saving: boolean;
  onRetry: () => void;
  setDraft: Dispatch<SetStateAction<CommandAccessPolicy | null>>;
  onClose: () => void;
  onReset: () => void;
  onSave: () => void;
}) {
  const dialogRef = useDialogFocus(Boolean(target), ".access-close", onClose);

  if (!target) return null;
  return (
    <div className="access-overlay">
      <section ref={dialogRef} className="access-dialog" role="dialog" aria-modal="true" aria-labelledby="command-access-title" tabIndex={-1}>
        <div className="access-heading">
          <div><p className="eyebrow">COMMAND POLICY</p><h2 id="command-access-title">Access for <span>/{target}</span></h2><p>Rules are checked by the bot on every command and component interaction.</p></div>
          <button type="button" className="access-close" onClick={onClose} aria-label="Close access editor"><Icon name="close" size={16} /></button>
        </div>
        {loading ? (
          <div className="access-grid access-grid-skeleton" role="status" aria-label="Loading this server’s role and channel rules">
            {Array.from({ length: 2 }, (_, index) => <div className="access-field" key={index}><Skeleton width="46%" height={8} /><Skeleton width="100%" height={38} radius={8} /><Skeleton width="100%" height={176} radius={8} /><Skeleton width={index === 0 ? "87%" : "74%"} height={8} /></div>)}
          </div>
        ) : options && draft ? (
          <>
            <div className="access-grid">
              <RoleAccessRules options={options.roles} policy={draft} onChange={setDraft} />
              <ChannelAccessRules options={options.channels} policy={draft} onChange={setDraft} />
            </div>
            <AccessPreview policy={draft} options={options} />
            <SaveChangesBar
              variant="inline"
              label={dirty ? "Unsaved policy changes" : "Policy is up to date"}
              ariaLabel="Command access policy changes"
              resetDisabled={!dirty}
              saveDisabled={!dirty}
              saving={saving}
              savingLabel="Saving…"
              onReset={onReset}
              onSave={onSave}
            />
          </>
        ) : (
          <div className="access-load-error"><SectionError message={error || "Role and channel settings could not be loaded."} status={errorStatus} onRetry={onRetry} /></div>
        )}
      </section>
    </div>
  );
}
