import { Icon } from "../../Icons";
import type { Page } from "../../Layout/navigation";

const CONFIGURATION_PAGES: { id: Page; label: string; icon: "commands" | "archive" | "settings" }[] = [
  { id: "commands", label: "Commands", icon: "commands" },
  { id: "archive", label: "Archive", icon: "archive" },
  { id: "settings", label: "Server settings", icon: "settings" },
];

export function ConfigurationNav({ active, canManageServer, onNavigate }: {
  active: Page;
  canManageServer: boolean;
  onNavigate: (page: Page) => void;
}) {
  return (
    <nav className="configuration-nav" aria-label="Server configuration">
      {CONFIGURATION_PAGES.filter(page => canManageServer || page.id === "settings").map(page => (
        <button
          key={page.id}
          type="button"
          className={"configuration-tab" + (active === page.id ? " active" : "")}
          aria-current={active === page.id ? "page" : undefined}
          onClick={() => onNavigate(page.id)}
        >
          <Icon name={page.icon} size={15} />
          <span>{page.label}</span>
        </button>
      ))}
    </nav>
  );
}
