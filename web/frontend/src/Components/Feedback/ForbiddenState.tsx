import { FeedbackState } from "./FeedbackState";

export function ForbiddenState({ message, onRefresh }: { message: string; onRefresh?: () => void }) {
  return <FeedbackState title="Permission check failed." message={message} icon="shield-check" actionLabel={onRefresh ? "Refresh access" : undefined} onAction={onRefresh} />;
}
