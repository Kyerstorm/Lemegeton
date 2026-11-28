import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

const matchMedia = vi.fn((media: string) => ({
  matches: false,
  media,
  onchange: null,
  addListener: vi.fn(),
  removeListener: vi.fn(),
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  dispatchEvent: vi.fn(() => false),
}));

Object.defineProperty(window, "matchMedia", {
  configurable: true,
  writable: true,
  value: matchMedia as typeof window.matchMedia,
});

afterEach(() => {
  cleanup();
});
