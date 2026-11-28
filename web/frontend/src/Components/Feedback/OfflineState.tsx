import { FeedbackState } from "./FeedbackState";

export function OfflineState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <FeedbackState title="Connection unavailable." message={message} icon="alert-circle" actionLabel={onRetry ? "Try again" : undefined} onAction={onRetry} />;
}
