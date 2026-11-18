import { MessageFlags } from "discord.js";
import { loadingMessage } from "../emoji.js";

type LoadingMode = "reply" | "update";

interface LoadingMessageResource {
  edit(payload: unknown): Promise<unknown>;
  delete(): Promise<unknown>;
}

interface LoadingInteraction {
  deferReply(options: { flags: MessageFlags }): Promise<unknown>;
  deferUpdate(): Promise<unknown>;
  reply(payload: unknown): Promise<unknown>;
  followUp(payload: unknown): Promise<LoadingMessageResource>;
  editReply(payload: unknown): Promise<unknown>;
  deleteReply(): Promise<unknown>;
}

function asEditPayload(payload: unknown): unknown {
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) return payload;
  const editPayload = { ...(payload as Record<string, unknown>) };
  delete editPayload.flags;
  delete editPayload.ephemeral;
  delete editPayload.fetchReply;
  return editPayload;
}

export async function withFakeLoading<T extends object, R>(
  interaction: T,
  activity: string,
  mode: LoadingMode,
  work: (interaction: T) => Promise<R>,
): Promise<R> {
  const target = interaction as unknown as LoadingInteraction;
  let loadingMessageResource: LoadingMessageResource | undefined;
  let loadingRemoved = false;
  let responseSent = false;

  const removeLoadingMessage = async (): Promise<void> => {
    if (!loadingMessageResource || loadingRemoved) return;
    loadingRemoved = true;
    await loadingMessageResource.delete().catch(() => undefined);
  };

  if (mode === "reply") {
    await target.deferReply({ flags: MessageFlags.Ephemeral });
    await target.editReply({ content: loadingMessage(activity) });
  } else {
    await target.deferUpdate();
    loadingMessageResource = await target.followUp({
      content: loadingMessage(activity),
      flags: MessageFlags.Ephemeral,
    });
  }

  const proxy = new Proxy(interaction, {
    get(original, property) {
      if (property === "deferReply" || property === "deferUpdate") {
        return async (): Promise<void> => undefined;
      }

      if (property === "reply" || property === "followUp") {
        return async (payload: unknown): Promise<unknown> => {
          responseSent = true;
          if (mode === "reply") return target.editReply(payload);
          return loadingMessageResource!.edit(asEditPayload(payload));
        };
      }

      if (property === "editReply") {
        return async (payload: unknown): Promise<unknown> => {
          responseSent = true;
          const result = await target.editReply(payload);
          if (mode === "update") await removeLoadingMessage();
          return result;
        };
      }

      if (property === "update" && mode === "update") {
        return async (payload: unknown): Promise<unknown> => {
          responseSent = true;
          try {
            return await target.editReply(payload);
          } finally {
            await removeLoadingMessage();
          }
        };
      }

      if (property === "deleteReply" && mode === "reply") {
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
    await new Promise<void>(resolve => setTimeout(resolve, 700));
    const result = await work(proxy);
    if (!responseSent && result !== false) {
      if (mode === "reply") await target.deleteReply().catch(() => undefined);
      else await removeLoadingMessage();
    } else if (!responseSent && result === false && mode === "update") {
      await removeLoadingMessage();
    }
    return result;
  } catch (error) {
    if (mode === "update") await removeLoadingMessage();
    throw error;
  }
}
