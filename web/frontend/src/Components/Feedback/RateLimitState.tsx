import { FeedbackState } from "./FeedbackState";

export function RateLimitState({ message, retryAfter, onRetry }: { message: string; retryAfter?: number; onRetry?: () => void }) {
  const wait = typeof retryAfter === "number" ? " Retry after " + retryAfter + " seconds." : "";
  return <FeedbackState title="Request limit reached." message={message + wait} icon="refresh" actionLabel={onRetry ? "Retry request" : undefined} onAction={onRetry} />;
}
