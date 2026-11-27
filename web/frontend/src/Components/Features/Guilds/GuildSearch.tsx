import { Input } from "../../UI";

export function GuildSearch({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <Input
      id="guild-search"
      type="search"
      label="FIND A SERVER"
      placeholder="Search manageable servers"
      autoComplete="off"
      maxLength={100}
      value={value}
      onChange={event => onChange(event.currentTarget.value)}
    />
  );
}
