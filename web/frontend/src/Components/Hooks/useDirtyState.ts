"use client";

import { useCallback, useMemo, useState } from "react";

export function useDirtyState<T>(
  initialValue: T,
  equals: (first: T, second: T) => boolean = Object.is,
) {
  const [saved, setSaved] = useState(initialValue);
  const [draft, setDraft] = useState(initialValue);
  const dirty = useMemo(() => !equals(draft, saved), [draft, saved, equals]);

  const reset = useCallback(() => setDraft(saved), [saved]);
  const replace = useCallback((value: T) => {
    setSaved(value);
    setDraft(value);
  }, []);
  const commit = useCallback((value: T) => {
    setSaved(value);
    setDraft(value);
  }, []);

  return { draft, setDraft, saved, dirty, reset, replace, commit };
}
