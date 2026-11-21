export const ICON_NAMES = [
  "overview","commands","atlas","extensions","audit","diagnostics","logs","integrations","database",
  "refresh","menu","home","retry","save","reset","shield-check","shield","upload","image","palette",
  "check","close","role","channel","lock","server","sparkles"
] as const;
export type IconName = (typeof ICON_NAMES)[number];
