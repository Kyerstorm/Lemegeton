"use client";

import { PickerMarkup } from "./PickerMarkup";
import { PICKER_STYLES } from "./PickerStyles";
import { useRoleStudio } from "./useRoleStudio";

export function RoleStudio() {
  const root = useRoleStudio();

  return <>
    <style dangerouslySetInnerHTML={{ __html: PICKER_STYLES }} />
    <div ref={root}><PickerMarkup /></div>
  </>;
}
