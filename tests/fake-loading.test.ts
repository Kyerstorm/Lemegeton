import assert from "node:assert/strict";
import test from "node:test";
import { withFakeLoading } from "../helpers/runtime/fake-loading.js";

test("reply-mode loading is replaced by the command response", async () => {
  const events: string[] = [];
  const target = {
    deferReply: async () => { events.push("defer"); },
    editReply: async (payload: { content?: string | null; embeds?: unknown[] }) => {
      events.push("edit:" + (payload.content ?? ""));
      return {};
    },
    deleteReply: async () => { events.push("delete"); },
  };

  await withFakeLoading(target, "Loading sample…", "reply", async current => {
    await (current as typeof target & { reply(payload: { content: string }): Promise<unknown> })
      .reply({ content: "Ready." });
    return true;
  });

  assert.equal(events[0], "defer");
  assert.match(events[1] ?? "", /Loading sample/);
  assert.equal(events[2], "edit:Ready.");
});

test("embed-only replies clear the temporary loading text", async () => {
  let finalContent: string | null | undefined;
  const target = {
    deferReply: async () => undefined,
    editReply: async (payload: { content?: string | null }) => { finalContent = payload.content; return {}; },
    deleteReply: async () => undefined,
  };

  await withFakeLoading(target, "Loading sample…", "reply", async current => {
    await (current as typeof target & { reply(payload: { embeds: unknown[] }): Promise<unknown> })
      .reply({ embeds: [{}] });
    return true;
  });

  assert.equal(finalContent, null);
});

test("component loading is removed after the original panel updates", async () => {
  const events: string[] = [];
  const loading = {
    edit: async (payload: { content?: string }) => { events.push("loading-edit:" + payload.content); return {}; },
    delete: async () => { events.push("loading-delete"); },
  };
  const target = {
    deferUpdate: async () => { events.push("defer-update"); },
    followUp: async () => { events.push("show-loading"); return loading; },
    editReply: async (payload: { content?: string }) => { events.push("panel-edit:" + payload.content); return {}; },
  };

  await withFakeLoading(target, "Updating sample…", "update", async current => {
    await (current as typeof target & { update(payload: { content: string }): Promise<unknown> })
      .update({ content: "Updated." });
    return true;
  });

  assert.deepEqual(events, [
    "defer-update",
    "show-loading",
    "panel-edit:Updated.",
    "loading-delete",
  ]);
});

test("component loading is cleaned up when an action is not handled", async () => {
  let removed = false;
  const target = {
    deferUpdate: async () => undefined,
    followUp: async () => ({ edit: async () => undefined, delete: async () => { removed = true; } }),
    editReply: async () => undefined,
  };

  const handled = await withFakeLoading(target, "Updating sample…", "update", async () => false);
  assert.equal(handled, false);
  assert.equal(removed, true);
});
