import { Icon } from "../Icons";

export interface MobileNavigationTriggerProps {
  open: boolean;
  onToggle: () => void;
}

export function MobileNavigationTrigger({ open, onToggle }: MobileNavigationTriggerProps) {
  return (
    <button
      className="icon-button mobile-menu"
      type="button"
      aria-label={open ? "Close navigation" : "Open navigation"}
      aria-expanded={open}
      aria-controls="sidebar"
      onClick={onToggle}
    >
      <Icon name={open ? "close" : "menu"} size={17} />
    </button>
  );
}

export function MobileNavigation({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null;
  return <button className="mobile-scrim active" type="button" aria-label="Close navigation" onClick={onClose} />;
}
