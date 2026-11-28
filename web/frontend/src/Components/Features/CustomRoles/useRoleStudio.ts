"use client";

import { useEffect, useRef } from "react";
import { mountCustomRolePicker } from "./picker";

export function useRoleStudio() {
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!root.current) return;
    return mountCustomRolePicker(root.current);
  }, []);

  return root;
}
