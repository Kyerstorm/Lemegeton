import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AccessPreview } from "../../src/Components/Features/Commands/AccessPreview";
import type { CommandAccessPolicy, CommandAccessResponse } from "../../src/Types/dashboard";

const options: CommandAccessResponse = {
  roles: [{ id: "role-1", name: "Moderators" }],
  channels: [{ id: "channel-1", name: "announcements", type: 0 }],
  policies: {},
};

const policy: CommandAccessPolicy = {
  role_mode: "include",
  role_ids: ["role-1"],
  channel_mode: "include",
  channel_ids: ["channel-1"],
  revision: 1,
};

describe("AccessPreview", () => {
  it("describes the selected role and channel rules", () => {
    render(<AccessPreview policy={policy} options={options} />);
    expect(screen.getByText("Effective access preview")).toBeTruthy();
    expect(screen.getByText("Only Moderators · Only #announcements. Both rules must allow the interaction.")).toBeTruthy();
  });

  it("makes empty allow-lists explicit", () => {
    render(
      <AccessPreview
        policy={{ ...policy, role_ids: [], channel_ids: [] }}
        options={options}
      />,
    );
    expect(screen.getByText(/No roles selected — access is denied/)).toBeTruthy();
    expect(screen.getByText(/No channels selected — access is denied/)).toBeTruthy();
  });

  it("marks IDs missing from current options as unknown", () => {
    render(
      <AccessPreview
        policy={{ ...policy, role_ids: ["missing-role"], channel_ids: ["missing-channel"] }}
        options={options}
      />,
    );
    expect(screen.getByText(/Only Unknown item/)).toBeTruthy();
    expect(screen.getByText(/Only #Unknown item/)).toBeTruthy();
  });
});
