"use client";

import { useEffect, useRef } from "react";
import { PickerMarkup } from "./PickerMarkup";
import { PICKER_STYLES } from "./PickerStyles";
import { mountCustomRolePicker } from "./picker";

export function CustomRolesClient() {
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!root.current) return;
    return mountCustomRolePicker(root.current);
  }, []);

  return <>
    <style dangerouslySetInnerHTML={{ __html: PICKER_STYLES }} />
    <div ref={root}><PickerMarkup /></div>
  </>;
}
