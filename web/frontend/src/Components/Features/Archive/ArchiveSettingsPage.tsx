"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../../../Lib/api";
import { dashboardRoutes } from "../../../Lib/routes";
import { validateArchiveSettings } from "../../../Lib/validation";
import type { ArchiveSettings, ArchiveSettingsResponse } from "../../../Types/dashboard";
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

function sameSettings(first: ArchiveSettings, second: ArchiveSettings): boolean {
  return JSON.stringify(first) === JSON.stringify(second);
}

function emptySettings(): ArchiveSettings {
  return {
    enabledCategories: [],
    uploadTypes: ["image"],
    uploadChannelId: null,
    legacyStorageChannelId: null,
    moderationChannelId: null,
    moderatorRoleId: null,
  };
}

export function ArchiveSettingsPage({ guildId, csrf, canManageServer, onNavigate, onDirtyChange }: {
  guildId: string;
  csrf: string;
  canManageServer: boolean;
  onNavigate: (page: Page) => void;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const [options, setOptions] = useState<ArchiveSettingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [loadStatus, setLoadStatus] = useState<number | null>(null);
  const { draft, setDraft, dirty, reset, replace } = useDirtyState(emptySettings(), sameSettings);

  const persist = useCallback(async (settings: ArchiveSettings) => {
    return api<{ settings: ArchiveSettings }>(
      dashboardRoutes.archiveSettings(guildId),
      csrf,
      { method: "PUT", body: JSON.stringify({ settings }) },
    );
  }, [csrf, guildId]);
  const { saving, error: saveError, setError: setSaveError, save } = useSaveChanges(persist);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const result = await api<ArchiveSettingsResponse>(
        dashboardRoutes.archiveSettings(guildId),
        csrf,
      );
      setOptions(result);
      replace(result.settings);
      setLoaded(true);
      setLoadStatus(null);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Archive settings could not be loaded.");
      setLoadStatus((error as { status?: number })?.status ?? null);
    } finally {
      setLoading(false);
    }
  }, [csrf, guildId, replace]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { onDirtyChange(dirty); }, [dirty, onDirtyChange]);
  useUnsavedChanges(dirty);

  const update = (patch: Partial<ArchiveSettings>) => {
    setSaveError("");
    setDraft(current => ({ ...current, ...patch }));
  };

  const toggleValue = (values: string[], value: string, checked: boolean) => (
    checked ? [...values, value] : values.filter(item => item !== value)
  );

  const handleSave = async () => {
    if (!dirty || saving) return;
    const validationError = validateArchiveSettings(draft, guildId);
    if (validationError) { setSaveError(validationError); return; }
    const result = await save(draft);
    if (!result) return;
    replace(result.settings);
    onDirtyChange(false);
  };

  if (loading && !loaded) {
    return (
      <section className="page configuration-page">
        <SectionHeading eyebrow="ARCHIVE CONFIGURATION" title={<>Community <span>Archive.</span></>} subtitle="Loading the selected server's Archive preferences." />
        <Skeleton height={140} />
        <Skeleton height={190} />
        <Skeleton height={150} />
      </section>
    );
  }

  return (
    <section className="page configuration-page">
      <SectionHeading
        eyebrow="ARCHIVE CONFIGURATION"
        title={<>Community <span>Archive.</span></>}
        subtitle="Choose which archive areas are available and where contributions are received and moderated."
      />
      <ConfigurationNav active="archive" canManageServer={canManageServer} onNavigate={onNavigate} />

      {loadError ? <SectionError message={loadError} status={loadStatus} onRetry={() => { void load(); }} /> : null}
      {options ? <>
        <div className="configuration-grid">
          <Card eyebrow="01 / CONTENT" title="Enabled categories">
            <FormSection title="Visible archive areas" description="At least one category must remain enabled.">
              <div
                className="configuration-choice-grid"
                role="group"
                aria-label="Enabled Archive categories"
                aria-describedby={draft.enabledCategories.length === 0 ? "archive-category-error" : undefined}
              >
                {options.categories.map(category => (
                  <label className="configuration-choice" key={category.value}>
                    <input
                      type="checkbox"
                      checked={draft.enabledCategories.includes(category.value)}
                      onChange={event => update({
                        enabledCategories: toggleValue(draft.enabledCategories, category.value, event.target.checked),
                      })}
                      disabled={!canManageServer || saving}
                    />
                    <span>{category.label}</span>
                  </label>
                ))}
              </div>
              {draft.enabledCategories.length === 0 ? <p id="archive-category-error" className="form-field-error" role="alert">Keep at least one Archive category enabled.</p> : null}
            </FormSection>
          </Card>

          <Card eyebrow="02 / CONTRIBUTIONS" title="Accepted uploads">
            <FormSection title="Upload formats" description="Links remain available independently of these attachment options.">
              <div className="configuration-choice-grid">
                {options.upload_types.map(kind => (
                  <label className="configuration-choice" key={kind.value}>
                    <input
                      type="checkbox"
                      checked={draft.uploadTypes.includes(kind.value)}
                      onChange={event => update({
                        uploadTypes: toggleValue(draft.uploadTypes, kind.value, event.target.checked),
                      })}
                      disabled={!canManageServer || saving}
                    />
                    <span>{kind.label}</span>
                  </label>
                ))}
              </div>
            </FormSection>
          </Card>
        </div>

        <Card eyebrow="03 / CHANNEL ROUTING" title="Archive channels">
          <div className="configuration-fields">
            <FormField label="Contribution channel" htmlFor="archive-upload-channel" hint="Optional channel for receiving Archive uploads.">
              <select
                id="archive-upload-channel"
                className="configuration-select"
                value={draft.uploadChannelId ?? ""}
                disabled={!canManageServer || saving}
                onChange={event => update({ uploadChannelId: event.target.value || null })}
              >
                <option value="">Not configured</option>
                {options.channels.map(channel => <option key={channel.id} value={channel.id}>#{channel.name}</option>)}
              </select>
            </FormField>
            <FormField label="Legacy storage channel" htmlFor="archive-storage-channel" hint="Keep any existing private storage channel assignment.">
              <select
                id="archive-storage-channel"
                className="configuration-select"
                value={draft.legacyStorageChannelId ?? ""}
                disabled={!canManageServer || saving}
                onChange={event => update({ legacyStorageChannelId: event.target.value || null })}
              >
                <option value="">Not configured</option>
                {options.channels.map(channel => <option key={channel.id} value={channel.id}>#{channel.name}</option>)}
              </select>
            </FormField>
            <FormField label="Moderation channel" htmlFor="archive-moderation-channel" hint="Optional destination for moderation activity.">
              <select
                id="archive-moderation-channel"
                className="configuration-select"
                value={draft.moderationChannelId ?? ""}
                disabled={!canManageServer || saving}
                onChange={event => update({ moderationChannelId: event.target.value || null })}
              >
                <option value="">Not configured</option>
                {options.channels.map(channel => <option key={channel.id} value={channel.id}>#{channel.name}</option>)}
              </select>
            </FormField>
            <FormField label="Archive moderator role" htmlFor="archive-moderator-role" hint="Optional role allowed to help moderate submissions.">
              <select
                id="archive-moderator-role"
                className="configuration-select"
                value={draft.moderatorRoleId ?? ""}
                disabled={!canManageServer || saving}
                onChange={event => update({ moderatorRoleId: event.target.value || null })}
              >
                <option value="">Not configured</option>
                {options.roles.map(role => <option key={role.id} value={role.id}>@{role.name}</option>)}
              </select>
            </FormField>
          </div>
          {!canManageServer ? <p className="configuration-note">Manage Server or Administrator permission is required to edit Archive settings.</p> : null}
        </Card>

        {saveError ? <SectionError message={saveError} onRetry={() => { void handleSave(); }} /> : null}
        {dirty ? <SaveChangesBar
          label="Unsaved Archive changes"
          detail="Changes apply to this server only."
          ariaLabel="Unsaved Archive configuration"
          saving={saving}
          saveDisabled={!canManageServer || draft.enabledCategories.length === 0}
          onReset={reset}
          onSave={() => { void handleSave(); }}
        /> : null}
      </> : null}
    </section>
  );
}
