export const ICON_NAMES = ["overview","commands","atlas","extensions","audit","diagnostics","logs","integrations","database","refresh","menu","home","retry"] as const;
export type IconName = (typeof ICON_NAMES)[number];
