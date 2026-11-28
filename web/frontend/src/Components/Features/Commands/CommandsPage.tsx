import type { Dispatch, SetStateAction } from "react";
import type { Command, CommandAccessPolicy, CommandAccessResponse } from "../../../Types/dashboard";
import type { Page } from "../../Layout/navigation";
import { Icon } from "../../Icons";
import { CommandList } from "./CommandList";
import { CommandSettings } from "./CommandSettings";
import { CommandAccessEditor } from "./CommandAccessEditor";
import { Input, Select, SectionHeading } from "../../UI";
import { SaveChangesBar } from "../../Forms/SaveChangesBar";
import { SectionError } from "../../Feedback/SectionError";
import { ConfigurationNav } from "./ConfigurationNav";

interface CommandsPageProps {
  eyebrow: string;
  canManageServer: boolean;
  onNavigate: (page: Page) => void;
  guildId: string;
  commands: Command[];
  filteredCommands: Command[];
  categories: string[];
  search: string;
  setSearch: (value: string) => void;
  category: string;
  setCategory: (value: string) => void;
  commandState: string;
  setCommandState: (value: string) => void;
  commandError: string;
  loading: boolean;
  loaded: boolean;
  errorStatus: number | null;
  onRetry: () => void;
  commandGuideUrl: (command: Command) => string;
  onCopyCommand: (command: Command) => void;
  onOpenCommandAccess: (command: Command) => void;
  accessLoading: boolean;
  accessError: string;
  accessErrorStatus: number | null;
  onRetryAccess: () => void;
  accessSaving: boolean;
  savingCommands: boolean;
  operationBusy: boolean;
  onToggleCommand: (command: Command) => void;
  onResetCommands: () => void;
  onSynchronizeCommands: () => void;
  commandDraftDirty: boolean;
  savedCommands: Command[];
  commandRevision: string;
  onResetCommandDraft: () => void;
  onSaveCommandDraft: () => void;
  accessTarget: string;
  accessOptions: CommandAccessResponse | null;
  accessDraft: CommandAccessPolicy | null;
  setAccessDraft: Dispatch<SetStateAction<CommandAccessPolicy | null>>;
  accessDraftDirty: boolean;
  onCloseCommandAccess: () => void;
  onResetCommandAccess: () => void;
  onSaveCommandAccess: () => void;
}

export function CommandsPage({
  eyebrow,
  canManageServer,
  onNavigate,
  guildId,
  commands,
  filteredCommands,
  categories,
  search,
  setSearch,
  category,
  setCategory,
  commandState,
  setCommandState,
  commandError,
  loading,
  loaded,
  errorStatus,
  onRetry,
  commandGuideUrl,
  onCopyCommand,
  onOpenCommandAccess,
  accessLoading,
  accessError,
  accessErrorStatus,
  onRetryAccess,
  accessSaving,
  savingCommands,
  operationBusy,
  onToggleCommand,
  onResetCommands,
  onSynchronizeCommands,
  commandDraftDirty,
  savedCommands,
  commandRevision,
  onResetCommandDraft,
  onSaveCommandDraft,
  accessTarget,
  accessOptions,
  accessDraft,
  setAccessDraft,
  accessDraftDirty,
  onCloseCommandAccess,
  onResetCommandAccess,
  onSaveCommandAccess,
}: CommandsPageProps) {
  const selectedPage = { eyebrow };
  const resetCommands = onResetCommands;
  const synchronizeCommands = onSynchronizeCommands;
  const toggleCommand = onToggleCommand;
  const copyCommandInvocation = onCopyCommand;
  const openCommandAccess = onOpenCommandAccess;
  const closeCommandAccess = onCloseCommandAccess;
  const resetCommandAccess = onResetCommandAccess;
  const saveCommandAccess = onSaveCommandAccess;
  const resetCommandDraft = onResetCommandDraft;
  const saveCommandDraft = onSaveCommandDraft;

  return (
    <section className="page">
        <SectionHeading eyebrow={selectedPage.eyebrow} title={<>Command <span>access.</span></>} subtitle="Changes apply to this guild and are confirmed only after the live bot synchronizes with Discord. Protected system commands stay enabled." actions={<CommandSettings guildId={guildId} busy={operationBusy} onReset={resetCommands} onPublish={synchronizeCommands} />} />
        <ConfigurationNav active="commands" canManageServer={canManageServer} onNavigate={onNavigate} />
        <div className="command-toolbar">
          <Input
            type="search"
            wrapperClassName="search-field"
            leading={<Icon name="search" size={15} />}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search name, description, category…"
            aria-label="Search registered commands"
            autoComplete="off"
          />
          <Select
            id="command-category-filter"
            wrapperClassName="filter-control"
            label="CATEGORY"
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            options={[{ value: "All", label: "All categories" }, ...categories.map(item => ({ value: item, label: item }))]}
          />
          <Select
            id="command-state-filter"
            wrapperClassName="filter-control"
            label="STATE"
            value={commandState}
            onChange={(event) => setCommandState(event.target.value)}
            options={[
              { value: "All", label: "All states" },
              { value: "Enabled", label: "Enabled" },
              { value: "Disabled", label: "Disabled" },
              { value: "Protected", label: "Protected" },
            ]}
          />
        </div>
        <div className="command-summary"><span>{filteredCommands.length} of {commands.length} registered commands</span><span>PER-GUILD CONFIGURATION</span></div>
         {commandError ? <SectionError message={commandError} status={errorStatus} onRetry={onRetry} /> : null}
        <CommandList
          commands={commands}
          filteredCommands={filteredCommands}
          loading={loading}
          loaded={loaded}
          error={commandError}
          saving={savingCommands}
          operationBusy={operationBusy}
          accessLoading={accessLoading}
          accessSaving={accessSaving}
          guideUrl={commandGuideUrl}
          onCopy={copyCommandInvocation}
          onOpenAccess={openCommandAccess}
          onToggle={toggleCommand}
        />
        <p className="footnote">Changes remain local until saved. The bot rechecks the server revision before publishing; protected commands cannot be changed.</p>
        <CommandAccessEditor
          target={accessTarget}
          loading={accessLoading}
          error={accessError}
          errorStatus={accessErrorStatus}
          options={accessOptions}
          draft={accessDraft}
          dirty={accessDraftDirty}
          saving={accessSaving}
          onRetry={onRetryAccess}
          setDraft={setAccessDraft}
          onClose={closeCommandAccess}
          onReset={resetCommandAccess}
          onSave={() => void saveCommandAccess()}
        />
        {commandDraftDirty ? <SaveChangesBar
          label="Unsaved changes"
          detail={commands.filter(item => !item.protected && savedCommands.find(saved => saved.fullname === item.fullname)?.enabled !== item.enabled).length + " command settings changed"}
          ariaLabel="Unsaved command changes"
          saving={savingCommands}
          resetDisabled={false}
          saveDisabled={!commandRevision}
          onReset={resetCommandDraft}
          onSave={() => void saveCommandDraft()}
        /> : null}
      </section>
  );
}
