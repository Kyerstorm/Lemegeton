"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../../../Lib/api";
import { dashboardRoutes } from "../../../Lib/routes";
import { validateServerSettingsUpdate } from "../../../Lib/validation";
import type { DashboardServerSettings } from "../../../Types/dashboard";
import type { Page } from "../../Layout/navigation";
import { ConfigurationNav } from "../Commands/ConfigurationNav";
import { FormField } from "../../Forms/FormField";
import { FormSection } from "../../Forms/FormSection";
import { SaveChangesBar } from "../../Forms/SaveChangesBar";
import { SectionError } from "../../Feedback/SectionError";
import { Card, SectionHeading, Skeleton } from "../../UI";
import { useDirtyState } from "../../Hooks/useDirtyState";
import { useSaveChanges } from "../../Hooks/useSaveChanges";
import { useUnsavedChanges } from "../../Hooks/useUnsavedChanges";

type ServerSetupDraft = {
  leave_action: "delete" | "retain" | null;
  language_code: string;
};

const EMPTY_SETTINGS: ServerSetupDraft = { leave_action: null, language_code: "" };

function sameSettings(first: ServerSetupDraft, second: ServerSetupDraft): boolean {
  return first.leave_action === second.leave_action && first.language_code === second.language_code;
}

export function ServerSettingsPage({ guildId, csrf, canManageServer, onNavigate, onDirtyChange, onSaved }: {
  guildId: string;
  csrf: string;
  canManageServer: boolean;
  onNavigate: (page: Page) => void;
  onDirtyChange: (dirty: boolean) => void;
  onSaved: (settings: DashboardServerSettings) => void;
}) {
  const [settings, setSettings] = useState<DashboardServerSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [loadStatus, setLoadStatus] = useState<number | null>(null);
  const { draft, setDraft, saved, dirty, reset, replace } = useDirtyState(EMPTY_SETTINGS, sameSettings);

  const persist = useCallback(async (next: ServerSetupDraft) => {
    const update: Partial<ServerSetupDraft> = {};
    if (next.leave_action !== saved.leave_action) update.leave_action = next.leave_action;
    if (next.language_code !== saved.language_code) update.language_code = next.language_code;
    const validationError = validateServerSettingsUpdate(update);
    if (validationError) throw new Error(validationError);
    return api<DashboardServerSettings>(
      dashboardRoutes.guildSettings(guildId),
      csrf,
      { method: "PUT", body: JSON.stringify(update) },
    );
  }, [csrf, guildId, saved]);
  const { saving, error: saveError, setError: setSaveError, save } = useSaveChanges(persist);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const result = await api<DashboardServerSettings>(
        dashboardRoutes.guildSettings(guildId),
        csrf,
      );
      setSettings(result);
      replace({
        leave_action: result.settings.leave_action,
        language_code: result.settings.language_code,
      });
      setLoaded(true);
      setLoadStatus(null);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Server settings could not be loaded.");
      setLoadStatus((error as { status?: number })?.status ?? null);
    } finally {
      setLoading(false);
    }
  }, [csrf, guildId, replace]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { onDirtyChange(dirty); }, [dirty, onDirtyChange]);
  useUnsavedChanges(dirty);

  const handleSave = async () => {
    if (!dirty || saving) return;
    const result = await save(draft);
    if (!result) return;
    setSettings(result);
    replace({
      leave_action: result.settings.leave_action,
      language_code: result.settings.language_code,
    });
    onSaved(result);
    onDirtyChange(false);
  };

  if (loading && !loaded) {
    return (
      <section className="page configuration-page">
        <SectionHeading eyebrow="SERVER SETTINGS" title={<>Server <span>setup.</span></>} subtitle="Loading server policy and language settings." />
        <Skeleton height={180} />
        <Skeleton height={135} />
      </section>
    );
  }

  return (
    <section className="page configuration-page">
      <SectionHeading
        eyebrow="SERVER SETTINGS"
        title={<>Server <span>setup.</span></>}
        subtitle="Set the server's data-retention preference and language before using the full dashboard."
      />
      <ConfigurationNav active="settings" canManageServer={canManageServer} onNavigate={onNavigate} />
      {loadError ? <SectionError message={loadError} status={loadStatus} onRetry={() => { void load(); }} /> : null}
      {settings ? <>
        <Card eyebrow="01 / DATA POLICY" title="When Lemegeton leaves">
          <FormSection title="Stored server data" description="This choice controls what happens to this server's retained Lemegeton data if the bot is removed.">
            <div className="configuration-fields">
              <FormField label="Data-retention choice" htmlFor="server-leave-action" hint="The inviter or a member with Manage Server permission can choose this.">
                <select
                  id="server-leave-action"
                  className="configuration-select"
                  value={draft.leave_action ?? ""}
                  disabled={!settings.can_choose_retention || saving || (saved.leave_action !== null && draft.leave_action === null)}
                  onChange={event => {
                    const value = event.target.value;
                    setSaveError("");
                    setDraft(current => ({ ...current, leave_action: value === "delete" || value === "retain" ? value : null }));
                  }}
                >
                  {saved.leave_action === null ? <option value="">Choose a retention policy</option> : null}
                  <option value="delete">Delete this server's stored data</option>
                  <option value="retain">Retain this server's data for a possible rejoin</option>
                </select>
              </FormField>
            </div>
            {!settings.can_choose_retention ? <p className="configuration-note">Only the person who invited Lemegeton or a member with Manage Server permission can change this choice.</p> : null}
          </FormSection>
        </Card>

        <Card eyebrow="02 / LANGUAGE" title="Server language">
          <FormSection title="Default language" description="Used by language-aware server messages and interfaces.">
            <FormField label="Language" htmlFor="server-language" hint="Search the list by typing after opening the selector.">
              <select
                id="server-language"
                className="configuration-select"
                value={draft.language_code}
                disabled={!settings.can_manage_server || saving}
                onChange={event => {
                  setSaveError("");
                  setDraft(current => ({ ...current, language_code: event.target.value }));
                }}
              >
                {saved.language_code === "" ? <option value="">Choose a language</option> : null}
                {settings.languages.map(language => <option key={language.code} value={language.code}>{language.label}</option>)}
              </select>
            </FormField>
            {!settings.can_manage_server ? <p className="configuration-note">Manage Server or Administrator permission is required to set the server language.</p> : null}
          </FormSection>
        </Card>

        {!settings.setup_complete ? <div className="configuration-note" role="status">
          The full dashboard remains locked until both the retention choice and server language are saved.
          {settings.can_choose_retention && !settings.can_manage_server ? " A server manager will need to choose the language." : ""}
        </div> : null}

        {saveError ? <SectionError message={saveError} onRetry={() => { void handleSave(); }} /> : null}
        {dirty ? <SaveChangesBar
          label="Unsaved server settings"
          detail="Only the settings changed here will be saved."
          ariaLabel="Unsaved server settings"
          saving={saving}
          saveDisabled={(!settings.can_choose_retention && draft.leave_action !== saved.leave_action)
            || (!settings.can_manage_server && draft.language_code !== saved.language_code)}
          onReset={reset}
          onSave={() => { void handleSave(); }}
        /> : null}
      </> : null}
    </section>
  );
}
