import { Icon } from "../../Icons";
import { Button, Card, SectionHeading, Skeleton, Tabs } from "../../UI";
import { SectionError } from "../../Feedback/SectionError";
import type { SectionLoadState } from "../../../Types/dashboard";
import type { PageMetadata } from "../../Layout/navigation";

type RuntimeLogFile = "bot.log" | "dashboard.log";

export function RuntimeLogs({ selectedPage, state, logName, logText, file, onChangeFile, onLoad }: {
  selectedPage: PageMetadata;
  state: SectionLoadState;
  logName: string;
  logText: string;
  file: RuntimeLogFile;
  onChangeFile: (file: RuntimeLogFile) => void;
  onLoad: () => void;
}) {
  return (
    <section className="page">
      <SectionHeading eyebrow={selectedPage.eyebrow} title={<>Logs, without <span>guesswork.</span></>} subtitle={selectedPage.subtitle} actions={<Button onClick={onLoad} disabled={state.loading}>Refresh log <Icon name="refresh" size={13} /></Button>} />
      <Tabs
        label="Runtime log source"
        value={file}
        options={[
          { value: "bot.log", label: "Bot runtime" },
          { value: "dashboard.log", label: "Dashboard service" },
        ]}
        onChange={value => onChangeFile(value === "dashboard.log" ? "dashboard.log" : "bot.log")}
      />
      <Card eyebrow="IN-MEMORY RUNTIME BUFFER" title={logName} className="log-panel" action={<span className="tag">LATEST 250 EVENTS</span>}>
        {state.error ? <SectionError message={state.error} status={state.errorStatus} onRetry={onLoad} /> : null}
        {!state.loaded && state.loading ? <div className="log-skeleton" role="status" aria-label="Loading runtime log entries">{Array.from({ length: 12 }, (_, index) => <Skeleton key={index} width={index % 4 === 0 ? "54%" : index % 3 === 0 ? "84%" : "96%"} height={8} />)}</div> : state.error && !state.loaded ? null : <pre className="log-output" tabIndex={0}>{logText || "No runtime log entries found."}</pre>}
      </Card>
    </section>
  );
}
