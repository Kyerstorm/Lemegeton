"use client";

import { useCallback, useRef, useState } from "react";
import { errorMessage } from "../../Lib/api";

export function useSaveChanges<T, R>(saveOperation: (value: T) => Promise<R>) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const busy = useRef(false);

  const save = useCallback(async (value: T): Promise<R | null> => {
    if (busy.current) return null;
    busy.current = true;
    setSaving(true);
    setError("");
    try {
      return await saveOperation(value);
    } catch (reason) {
      setError(errorMessage(reason));
      return null;
    } finally {
      busy.current = false;
      setSaving(false);
    }
  }, [saveOperation]);

  return { saving, error, setError, save };
}
