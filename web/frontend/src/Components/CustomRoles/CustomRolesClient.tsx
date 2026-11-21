"use client";

import { useEffect, useRef } from "react";
import { PICKER_MARKUP } from "./PickerMarkup";
import { PICKER_STYLES } from "./PickerStyles";
import { mountCustomRolePicker } from "./picker";

export function CustomRolesClient() {
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!root.current) return;
    return mountCustomRolePicker();
  }, []);

  return <>
    <style dangerouslySetInnerHTML={{ __html: PICKER_STYLES }} />
    <div ref={root} dangerouslySetInnerHTML={{ __html: PICKER_MARKUP }} />
  </>;
}
