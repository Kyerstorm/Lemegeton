import assert from "node:assert/strict";
import test from "node:test";
import { withFakeLoading } from "../helpers/runtime/fake-loading.js";

function makeMessage() {
  return {
    content: "Original panel",
    embeds: [{ toJSON: () => ({ title: "Original embed" }) }],
    components: [{ toJSON: () => ({ type: 1, components: [] }) }],
    attachments: {
      values: () => [{ id: "attachment-1", name: "panel.png" }],
    },
  };
}

test("reply mode uses one deferred message for loading and the final response", async () => {
  const events: string[] = [];
  const target = {
    deferReply: async () => { events.push("defer"); },
    editReply: async (payload: { content?: string | null; embeds?: unknown[] }) => {
      events.push("edit:" + (payload.content ?? ""));
      return {};
    },
    followUp: async () => { events.push("follow-up"); return {}; },
    deleteReply: async () => { events.push("delete"); },
  };

  await withFakeLoading(target, "Fetching media…", "reply", async current => {
    await (current as typeof target & { reply(payload: { content: string }): Promise<unknown> })
      .reply({ content: "Results ready." });
    return true;
  });

  assert.deepEqual(events, ["defer", "edit:Fetching media…", "edit:Results ready."]);
});

test("embed-only replies clear the temporary loading text", async () => {
  let finalPayload: { content?: string | null; embeds?: unknown[] } | undefined;
  const target = {
    deferReply: async () => undefined,
    editReply: async (payload: { content?: string | null; embeds?: unknown[] }) => {
      finalPayload = payload;
      return {};
    },
    followUp: async () => ({}),
    deleteReply: async () => undefined,
  };

  await withFakeLoading(target, "Loading help…", "reply", async current => {
    await (current as typeof target & { reply(payload: { embeds: unknown[] }): Promise<unknown> })
      .reply({ embeds: [{}] });
    return true;
  });

  assert.equal(finalPayload?.content, null);
  assert.deepEqual(finalPayload?.embeds, [{}]);
});

test("private component work uses one ephemeral loading response without changing the panel", async () => {
  const events: string[] = [];
  const target = {
    deferReply: async () => { events.push("defer-reply"); },
    editReply: async (payload: { content?: string | null }) => {
      events.push("edit:" + (payload.content ?? ""));
      return {};
    },
    followUp: async () => { events.push("follow-up"); return {}; },
    deleteReply: async () => { events.push("delete"); },
    message: makeMessage(),
  };

  await withFakeLoading(target, "Fetching media results…", "reply", async current => {
    await (current as typeof target & { reply(payload: { content: string }): Promise<unknown> })
      .reply({ content: "Fetching media results…" });
    await current.editReply({ content: "Private results ready." });
    return true;
  });

  assert.deepEqual(events, [
    "defer-reply",
    "edit:Fetching media results…",
    "edit:Private results ready.",
  ]);
});

test("component updates edit the original interaction message in place", async () => {
  const events: string[] = [];
  const target = {
    deferUpdate: async () => { events.push("defer-update"); },
    editReply: async (payload: { content?: string | null; embeds?: unknown[]; components?: unknown[] }) => {
      events.push("edit:" + (payload.content ?? ""));
      return {};
    },
    followUp: async () => { events.push("follow-up"); return {}; },
    message: makeMessage(),
  };

  await withFakeLoading(target, "Fetching Archive entries…", "update", async current => {
    await (current as typeof target & { update(payload: { embeds: unknown[] }): Promise<unknown> })
      .update({ embeds: [{ title: "Updated panel" }] });
    return true;
  });

  assert.deepEqual(events, ["defer-update", "edit:Fetching Archive entries…", "edit:"]);
});

test("component replies restore the original panel and send only the final reply separately", async () => {
  const events: string[] = [];
  const target = {
    deferUpdate: async () => { events.push("defer-update"); },
    editReply: async (payload: { content?: string | null; embeds?: unknown[]; components?: unknown[]; attachments?: unknown[] }) => {
      events.push("edit:" + (payload.content ?? ""));
      return {};
    },
    followUp: async (payload: { content: string }) => {
      events.push("follow-up:" + payload.content);
      return {};
    },
    message: makeMessage(),
  };

  await withFakeLoading(target, "Saving your vote…", "update", async current => {
    await (current as typeof target & { reply(payload: { content: string }): Promise<unknown> })
      .reply({ content: "Your vote was saved." });
    return true;
  });

  assert.deepEqual(events, [
    "defer-update",
    "edit:Saving your vote…",
    "follow-up:Your vote was saved.",
    "edit:Original panel",
  ]);
});

test("unhandled component actions restore the original panel", async () => {
  const events: string[] = [];
  const target = {
    deferUpdate: async () => { events.push("defer-update"); },
    editReply: async (payload: { content?: string | null }) => {
      events.push("edit:" + (payload.content ?? ""));
      return {};
    },
    followUp: async () => { events.push("follow-up"); return {}; },
    message: makeMessage(),
  };

  const handled = await withFakeLoading(target, "Updating settings…", "update", async () => false);

  assert.equal(handled, false);
  assert.deepEqual(events, [
    "defer-update",
    "edit:Updating settings…",
    "edit:Original panel",
  ]);
});

test("component failures restore the original panel before the error response", async () => {
  const events: string[] = [];
  const target = {
    deferUpdate: async () => { events.push("defer-update"); },
    editReply: async (payload: { content?: string | null }) => {
      events.push("edit:" + (payload.content ?? ""));
      return {};
    },
    followUp: async () => { events.push("follow-up"); return {}; },
    message: makeMessage(),
  };

  await assert.rejects(
    withFakeLoading(target, "Updating role configuration…", "update", async () => {
      throw new Error("role update failed");
    }),
    /role update failed/,
  );

  assert.deepEqual(events, [
    "defer-update",
    "edit:Updating role configuration…",
    "edit:Original panel",
  ]);
});
