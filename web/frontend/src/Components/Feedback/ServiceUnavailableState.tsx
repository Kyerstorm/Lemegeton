import { FeedbackState } from "./FeedbackState";

export function ServiceUnavailableState({ message, onRetry, reportHref }: {
  message: string;
  onRetry?: () => void;
  reportHref?: string;
}) {
  return (
    <FeedbackState
      title="Service temporarily unavailable."
      message={message}
      icon="server"
      actionLabel={onRetry ? "Try again" : undefined}
      onAction={onRetry}
      reportHref={reportHref}
    />
  );
}
