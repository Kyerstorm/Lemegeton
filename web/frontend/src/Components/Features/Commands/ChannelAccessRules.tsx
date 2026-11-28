import { MultiSelect, Select } from "../../UI";
import type { CommandAccessPolicy, CommandAccessResponse } from "../../../Types/dashboard";

export function ChannelAccessRules({ options, policy, onChange }: {
  options: CommandAccessResponse["channels"];
  policy: CommandAccessPolicy;
  onChange: (next: (current: CommandAccessPolicy | null) => CommandAccessPolicy | null) => void;
}) {
  return (
    <div className="access-field">
      <Select
        id="access-channel-mode"
        wrapperClassName="access-field-select-control"
        label="WHERE CAN IT RUN"
        value={policy.channel_mode}
        onChange={event => onChange(current => current ? { ...current, channel_mode: event.target.value as CommandAccessPolicy["channel_mode"] } : current)}
        options={[
          { value: "all", label: "All supported channels" },
          { value: "include", label: "Only selected channels" },
          { value: "exclude", label: "All except selected channels" },
        ]}
      />
      <MultiSelect
        aria-label="Select channels"
        aria-describedby="access-channel-help"
        size={7}
        value={policy.channel_ids}
        onChange={event => onChange(current => current ? { ...current, channel_ids: Array.from(event.currentTarget.selectedOptions, option => option.value) } : current)}
        options={options.map(channel => ({ value: channel.id, label: "#" + channel.name }))}
      />
      <small id="access-channel-help">Only server text-capable channels are listed. An empty include list denies all channels.</small>
    </div>
  );
}
