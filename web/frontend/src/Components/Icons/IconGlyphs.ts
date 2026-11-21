import type { ComponentType } from "react";
import { OverviewIcon, CommandsIcon, AtlasIcon, ExtensionsIcon, AuditIcon, DiagnosticsIcon, LogsIcon, IntegrationsIcon, DatabaseIcon } from "./dashboard";
import { RefreshIcon, RetryIcon, SaveIcon, ResetIcon, UploadIcon, CopyIcon, CloseIcon, ArrowUpRightIcon, ExternalLinkIcon } from "./actions";
import { MenuIcon, HomeIcon, ChevronRightIcon, SearchIcon } from "./navigation";
import { ShieldCheckIcon, ShieldIcon, LockIcon } from "./security";
import { CheckIcon, CheckCircleIcon, AlertCircleIcon, ActivityIcon } from "./status";
import { ImageIcon, PaletteIcon, RoleIcon, ChannelIcon, ServerIcon, SparklesIcon } from "./media";
import type { IconName } from "./IconRegistry";

export const ICON_GLYPHS: Record<IconName, ComponentType> = {
  "overview": OverviewIcon,
  "commands": CommandsIcon,
  "atlas": AtlasIcon,
  "extensions": ExtensionsIcon,
  "audit": AuditIcon,
  "diagnostics": DiagnosticsIcon,
  "logs": LogsIcon,
  "integrations": IntegrationsIcon,
  "database": DatabaseIcon,
  "refresh": RefreshIcon,
  "retry": RetryIcon,
  "save": SaveIcon,
  "reset": ResetIcon,
  "upload": UploadIcon,
  "copy": CopyIcon,
  "close": CloseIcon,
  "arrow-up-right": ArrowUpRightIcon,
  "external-link": ExternalLinkIcon,
  "menu": MenuIcon,
  "home": HomeIcon,
  "chevron-right": ChevronRightIcon,
  "search": SearchIcon,
  "shield-check": ShieldCheckIcon,
  "shield": ShieldIcon,
  "lock": LockIcon,
  "check": CheckIcon,
  "check-circle": CheckCircleIcon,
  "alert-circle": AlertCircleIcon,
  "activity": ActivityIcon,
  "image": ImageIcon,
  "palette": PaletteIcon,
  "role": RoleIcon,
  "channel": ChannelIcon,
  "server": ServerIcon,
  "sparkles": SparklesIcon,
};
