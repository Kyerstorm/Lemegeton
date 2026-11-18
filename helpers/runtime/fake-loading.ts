import { MessageFlags } from "discord.js";
import { loadingMessage } from "../emoji.js";

type LoadingMode = "reply" | "update";

interface LoadingMessageSnapshot {
  content: string;
  embeds: Array<{ toJSON(): unknown }>;
  components: Array<{ toJSON(): unknown }>;
  attachments: {
    values(): Iterable<{ id: string; name: string | null }>;
  };
}

interface LoadingInteraction {
  deferReply(options: { flags: MessageFlags }): Promise<unknown>;
  deferUpdate(): Promise<unknown>;
  reply(payload: unknown): Promise<unknown>;
  followUp(payload: unknown): Promise<unknown>;
  editReply(payload: unknown): Promise<unknown>;
  deleteReply(): Promise<unknown>;
  message?: LoadingMessageSnapshot;
}

function asEditPayload(payload: unknown, clearLoadingContent = false): unknown {
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) return payload;
  const editPayload = { ...(payload as Record<string, unknown>) };
  delete editPayload.flags;
  delete editPayload.ephemeral;
  delete editPayload.fetchReply;
  if (clearLoadingContent && !("content" in editPayload)) editPayload.content = null;
  return editPayload;
}

function messageSnapshot(message: LoadingMessageSnapshot | undefined): Record<string, unknown> | null {
  if (!message) return null;
  const attachments = [...message.attachments.values()].map(attachment => ({
    id: attachment.id,
    filename: attachment.name ?? undefined,
  }));
  return {
    content: message.content || null,
    embeds: message.embeds.map(embed => embed.toJSON()),
    components: message.components.map(component => component.toJSON()),
    ...(attachments.length ? { attachments } : {}),
  };
}

export async function withFakeLoading<T extends object, R>(
  interaction: T,
  activity: string,
  mode: LoadingMode,
  work: (interaction: T) => Promise<R>,
): Promise<R> {
  const target = interaction as unknown as LoadingInteraction;
  const originalMessage = mode === "update" ? messageSnapshot(target.message) : null;
  let responseSent = false;
  let originalRestored = false;

  const restoreOriginalMessage = async (): Promise<void> => {
    if (!originalMessage || originalRestored) return;
    originalRestored = true;
    await target.editReply(originalMessage);
  };

  if (mode === "reply") {
    await target.deferReply({ flags: MessageFlags.Ephemeral });
    await target.editReply({ content: loadingMessage(activity) });
  } else {
    await target.deferUpdate();
    await target.editReply({
      content: loadingMessage(activity),
      embeds: [],
      components: [],
      allowedMentions: { parse: [] },
    });
  }

  const proxy = new Proxy(interaction, {
    get(original, property) {
      if (property === "deferReply" || property === "deferUpdate") {
        return async (): Promise<void> => undefined;
      }

      if (property === "reply") {
        return async (payload: unknown): Promise<unknown> => {
          responseSent = true;
          if (mode === "reply") return target.editReply(asEditPayload(payload, true));
          try {
            return await target.followUp(payload);
          } finally {
            await restoreOriginalMessage();
          }
        };
      }

      if (property === "followUp") {
        return async (payload: unknown): Promise<unknown> => {
          responseSent = true;
          try {
            return await target.followUp(payload);
          } finally {
            if (mode === "update") await restoreOriginalMessage();
          }
        };
      }

      if (property === "editReply" || property === "update") {
        return async (payload: unknown): Promise<unknown> => {
          responseSent = true;
          return target.editReply(asEditPayload(payload, true));
        };
      }

      if (property === "deleteReply") {
        return async (): Promise<unknown> => {
          responseSent = true;
          return target.deleteReply();
        };
      }

      const value = Reflect.get(original, property, original) as unknown;
      return typeof value === "function" ? value.bind(original) : value;
    },
  }) as T;

  try {
    const result = await work(proxy);
    if (mode === "update" && !responseSent) await restoreOriginalMessage();
    return result;
  } catch (error) {
    if (mode === "update" && !originalRestored) {
      await restoreOriginalMessage().catch(() => undefined);
    }
    throw error;
  }
}
