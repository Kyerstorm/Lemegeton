import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useDirtyState } from "../../src/Components/Hooks/useDirtyState";
import { useReducedMotion } from "../../src/Components/Hooks/useReducedMotion";
import { useSaveChanges } from "../../src/Components/Hooks/useSaveChanges";
import { useUnsavedChanges } from "../../src/Components/Hooks/useUnsavedChanges";

afterEach(() => vi.unstubAllGlobals());

describe("useDirtyState", () => {
  it("tracks edits, resets to the saved value and commits confirmed values", () => {
    const equals = (first: { enabled: boolean }, second: { enabled: boolean }) =>
      first.enabled === second.enabled;
    const { result } = renderHook(() => useDirtyState({ enabled: true }, equals));

    expect(result.current.dirty).toBe(false);
    act(() => result.current.setDraft({ enabled: false }));
    expect(result.current.dirty).toBe(true);

    act(() => result.current.reset());
    expect(result.current.draft).toEqual({ enabled: true });
    expect(result.current.dirty).toBe(false);

    act(() => result.current.commit({ enabled: false }));
    expect(result.current.saved).toEqual({ enabled: false });
    expect(result.current.draft).toEqual({ enabled: false });
    expect(result.current.dirty).toBe(false);

    act(() => result.current.replace({ enabled: true }));
    expect(result.current.saved).toEqual({ enabled: true });
    expect(result.current.dirty).toBe(false);
  });
});

describe("useSaveChanges", () => {
  it("returns a successful result and clears the saving state", async () => {
    const operation = vi.fn(async (value: string) => "saved:" + value);
    const { result } = renderHook(() => useSaveChanges(operation));
    let response: string | null = null;

    await act(async () => {
      response = await result.current.save("draft");
    });

    expect(response).toBe("saved:draft");
    expect(operation).toHaveBeenCalledWith("draft");
    expect(result.current.saving).toBe(false);
    expect(result.current.error).toBe("");
  });

  it("prevents overlapping writes while a request is pending", async () => {
    let resolveOperation!: (value: string) => void;
    const operation = vi.fn(() => new Promise<string>(resolve => {
      resolveOperation = resolve;
    }));
    const { result } = renderHook(() => useSaveChanges(operation));
    let first!: Promise<string | null>;

    act(() => { first = result.current.save("first"); });
    expect(result.current.saving).toBe(true);

    let second: string | null = "not-set";
    await act(async () => { second = await result.current.save("second"); });
    expect(second).toBeNull();
    expect(operation).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveOperation("stored");
      await expect(first).resolves.toBe("stored");
    });
    expect(result.current.saving).toBe(false);
  });

  it("exposes save failures without throwing", async () => {
    const operation = vi.fn(async (_value: string): Promise<string> => {
      throw new Error("Revision conflict.");
    });
    const { result } = renderHook(() => useSaveChanges(operation));
    let response: string | null = "not-set";

    await act(async () => { response = await result.current.save("unsaved draft"); });

    expect(response).toBeNull();
    expect(result.current.error).toBe("Revision conflict.");
    expect(result.current.saving).toBe(false);
    expect(operation).toHaveBeenCalledWith("unsaved draft");
  });
});

describe("useUnsavedChanges", () => {
  it("adds a beforeunload guard only while the draft is dirty", () => {
    const { rerender, unmount } = renderHook(
      ({ dirty }) => useUnsavedChanges(dirty),
      { initialProps: { dirty: false } },
    );

    const clean = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(clean);
    expect(clean.defaultPrevented).toBe(false);

    rerender({ dirty: true });
    const dirty = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(dirty);
    expect(dirty.defaultPrevented).toBe(true);

    rerender({ dirty: false });
    const reset = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(reset);
    expect(reset.defaultPrevented).toBe(false);
    unmount();
  });
});

describe("useReducedMotion", () => {
  it("tracks preference changes and removes its listener on unmount", () => {
    let reduced = false;
    let onChange: (() => void) | undefined;
    const media = {
      get matches() { return reduced; },
      media: "(prefers-reduced-motion: reduce)",
      addEventListener: vi.fn((_type: string, listener: () => void) => { onChange = listener; }),
      removeEventListener: vi.fn(),
    } as unknown as MediaQueryList;
    vi.stubGlobal("matchMedia", vi.fn(() => media));

    const { result, unmount } = renderHook(() => useReducedMotion());
    expect(result.current).toBe(false);

    act(() => {
      reduced = true;
      onChange?.();
    });
    expect(result.current).toBe(true);

    unmount();
    expect(media.removeEventListener).toHaveBeenCalledWith("change", onChange);
  });
});
