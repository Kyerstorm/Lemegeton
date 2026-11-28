import { MultiSelect, Select } from "../../UI";
import type { CommandAccessPolicy, CommandAccessResponse } from "../../../Types/dashboard";

export function RoleAccessRules({ options, policy, onChange }: {
  options: CommandAccessResponse["roles"];
  policy: CommandAccessPolicy;
  onChange: (next: (current: CommandAccessPolicy | null) => CommandAccessPolicy | null) => void;
}) {
  return (
    <div className="access-field">
      <Select
        id="access-role-mode"
        wrapperClassName="access-field-select-control"
        label="WHO CAN USE IT"
        value={policy.role_mode}
        onChange={event => onChange(current => current ? { ...current, role_mode: event.target.value as CommandAccessPolicy["role_mode"] } : current)}
        options={[
          { value: "everyone", label: "Everyone" },
          { value: "include", label: "Only selected roles" },
          { value: "exclude", label: "Everyone except selected roles" },
        ]}
      />
      <MultiSelect
        aria-label="Select roles"
        aria-describedby="access-role-help"
        size={7}
        value={policy.role_ids}
        onChange={event => onChange(current => current ? { ...current, role_ids: Array.from(event.currentTarget.selectedOptions, option => option.value) } : current)}
        options={options.map(role => ({ value: role.id, label: role.name }))}
      />
      <small id="access-role-help">With “Only selected roles”, an empty selection blocks everyone. Excluded roles are denied.</small>
    </div>
  );
}
