import { ForbiddenState } from "./ForbiddenState";
import { OfflineState } from "./OfflineState";
import { RateLimitState } from "./RateLimitState";
import { ServiceUnavailableState } from "./ServiceUnavailableState";
import { FeedbackState } from "./FeedbackState";

export interface SectionErrorProps {
  message: string;
  status?: number | null;
  onRetry: () => void;
}

export function SectionError({ message, status, onRetry }: SectionErrorProps) {
  if (status === 0) return <OfflineState message={message} onRetry={onRetry} />;
  if (status === 403 || status === 428) return <ForbiddenState message={message} onRefresh={() => window.location.reload()} />;
  if (status === 429) return <RateLimitState message={message} onRetry={onRetry} />;
  if (status === 503) return <ServiceUnavailableState message={message} onRetry={onRetry} reportHref="/issues" />;
  return (
    <FeedbackState
      title="Unable to load this section."
      message={message}
      actionLabel="Try again"
      onAction={onRetry}
      reportHref={status === null || status === undefined || status >= 500 ? "/issues" : undefined}
    />
  );
}
