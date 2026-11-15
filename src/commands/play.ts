import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  EmbedBuilder,
  MessageFlags,
  ModalBuilder,
  SlashCommandBuilder,
  StringSelectMenuBuilder,
  TextInputBuilder,
  TextInputStyle,
  type ButtonInteraction,
  type ChatInputCommandInteraction,
  type ModalSubmitInteraction,
  type StringSelectMenuInteraction,
  type TextChannel,
} from "discord.js";
import { emoji } from "../../helpers/emoji.js";
import type { FeatureCommand } from "../../helpers/commands/command.js";
import { createInteractionIssueLog, issueHashNotice } from "../../helpers/runtime/issue-logs.js";
import { homeEmbed } from "../../helpers/runtime/discord.js";
import {
  addQuizQuestion,
  advanceGame,
  answerGameQuestion,
  createQuizPack,
  getCurrentGameQuestion,
  getQuizQuestionForEditing,
  getQuizQuestionRevisionHistory,
  editQuizQuestion,
  getGameLeaderboard,
  getGameSession,
  revealGameClue,
  joinGame,
  listQuizPacks,
  pendingQuizQuestions,
  reviewQuizPack,
  reviewQuizQuestion,
  startGame,
  type GameMode,
  type GameLeaderboardEntry,
  type EditableQuizQuestion,
} from "../../helpers/runtime/games.js";
import { query } from "../../database.js";
import { isGuildManager, isValidHttpsUrl, safeDisplay } from "../../helpers/security/security.js";

function playHome(): { embeds: EmbedBuilder[]; components: ActionRowBuilder<ButtonBuilder>[] } {
  return {
    embeds: [homeEmbed(
      "Media Games",
      "Play source-backed community quizzes and guessing games. Question packs and individual questions are reviewed before they can enter a live session. Scores are persisted by round, and only the host can advance the game.",
      [
        { name: "Build a pack", value: "Contribute questions with a provider source link.", inline: true },
        { name: "Review", value: "Server moderators approve packs and questions.", inline: true },
        { name: "Play", value: "Start a solo or multiplayer session from an approved pack.", inline: true },
      ],
    )],
    components: [
      new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId("play:create-pack").setLabel("Create question pack").setStyle(ButtonStyle.Primary),
        new ButtonBuilder().setCustomId("play:add-question").setLabel("Add a question").setStyle(ButtonStyle.Success),
        new ButtonBuilder().setCustomId("play:start").setLabel("Start a game").setStyle(ButtonStyle.Primary),
        new ButtonBuilder().setCustomId("play:packs").setLabel("Browse packs").setStyle(ButtonStyle.Secondary),
        new ButtonBuilder().setCustomId("play:review").setLabel("Review queue").setStyle(ButtonStyle.Secondary),
      ),
      new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId("play:start-team").setLabel("Competitive teams").setStyle(ButtonStyle.Primary),
        new ButtonBuilder().setCustomId("play:start-coop").setLabel("Co-op game").setStyle(ButtonStyle.Success),
      ),
    ],
  };
}

function packModal(): ModalBuilder {
  return new ModalBuilder()
    .setCustomId("play:create-pack")
    .setTitle("Create a media quiz pack")
    .addComponents(
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("title").setLabel("Pack title").setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(160),
      ),
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("description").setLabel("What is this pack about?").setStyle(TextInputStyle.Paragraph).setRequired(false).setMaxLength(800),
      ),
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("mode").setLabel("Mode: trivia, guessing or mystery").setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(24).setValue("trivia"),
      ),
    );
}

function questionModal(packId = "", packMode = "trivia"): ModalBuilder {
  const rows: ActionRowBuilder<TextInputBuilder>[] = [];
  if (!packId) rows.push(new ActionRowBuilder<TextInputBuilder>().addComponents(
    new TextInputBuilder().setCustomId("pack_id").setLabel("Question pack ID").setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(20),
  ));
  rows.push(
    new ActionRowBuilder<TextInputBuilder>().addComponents(new TextInputBuilder().setCustomId("question").setLabel("Question (no long copyrighted passages)").setStyle(TextInputStyle.Paragraph).setRequired(true).setMaxLength(500)),
    new ActionRowBuilder<TextInputBuilder>().addComponents(new TextInputBuilder().setCustomId("answer").setLabel("Correct answer").setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(200)),
    new ActionRowBuilder<TextInputBuilder>().addComponents(new TextInputBuilder().setCustomId("accepted").setLabel(packMode === "trivia" ? "Alternative accepted answers" : "Layered clues (category: clue, one per line)").setStyle(TextInputStyle.Paragraph).setRequired(false).setMaxLength(500)),
    new ActionRowBuilder<TextInputBuilder>().addComponents(new TextInputBuilder().setCustomId("source").setLabel("HTTPS source link").setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(400)),
  );
  if (packId) rows.push(new ActionRowBuilder<TextInputBuilder>().addComponents(new TextInputBuilder().setCustomId("difficulty").setLabel("Difficulty: easy, standard, hard or expert").setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(12).setValue("standard")));
  return new ModalBuilder().setCustomId(`play:add-question:${packId || "select"}`).setTitle("Contribute a source-backed question").addComponents(...rows);
}
function editQuestionModal(question: EditableQuizQuestion): ModalBuilder {
  const accepted = question.accepted_answers.filter(value => value !== question.correct_answer).join(", ");
  const acceptedInput = new TextInputBuilder().setCustomId("accepted").setLabel("Alternative accepted answers").setStyle(TextInputStyle.Short).setRequired(false).setMaxLength(500);
  if (accepted) acceptedInput.setValue(accepted.slice(0, 500));
  return new ModalBuilder().setCustomId(`play:edit-question:${question.id}`).setTitle("Revise question").addComponents(
    new ActionRowBuilder<TextInputBuilder>().addComponents(new TextInputBuilder().setCustomId("question").setLabel("Question").setStyle(TextInputStyle.Paragraph).setRequired(true).setMaxLength(500).setValue(question.question.slice(0, 500))),
    new ActionRowBuilder<TextInputBuilder>().addComponents(new TextInputBuilder().setCustomId("answer").setLabel("Correct answer").setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(200).setValue(question.correct_answer.slice(0, 200))),
    new ActionRowBuilder<TextInputBuilder>().addComponents(acceptedInput),
    new ActionRowBuilder<TextInputBuilder>().addComponents(new TextInputBuilder().setCustomId("source").setLabel("HTTPS source link").setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(400).setValue(question.source_url.slice(0, 400))),
    new ActionRowBuilder<TextInputBuilder>().addComponents(new TextInputBuilder().setCustomId("difficulty").setLabel("Difficulty: easy, standard, hard or expert").setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(12).setValue(question.difficulty)),
  );
}
function answerModal(sessionId: string): ModalBuilder {
  return new ModalBuilder()
    .setCustomId(`play:answer:${sessionId}`)
    .setTitle("Submit your answer")
    .addComponents(new ActionRowBuilder<TextInputBuilder>().addComponents(
      new TextInputBuilder().setCustomId("answer").setLabel("Your answer").setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(200),
    ));
}

function questionEmbed(title: string, question: string, sourceUrl: string, round: number, total: number, difficulty = "standard"): EmbedBuilder {
  return new EmbedBuilder()
    .setColor(0x5865f2)
    .setTitle(title)
    .setDescription(question)
    .addFields(
      { name: "Round", value: `${round} / ${total}`, inline: true },
      { name: "Source", value: `[Open provider source](${sourceUrl})`, inline: true },
      { name: "Difficulty", value: difficulty.toUpperCase(), inline: true },
    )
    .setFooter({ text: "Answers are private until submitted · One answer per player per round" });
}

function gameButtons(sessionId: string, packMode: string = "trivia"): ActionRowBuilder<ButtonBuilder>[] {
  const rows: ActionRowBuilder<ButtonBuilder>[] = [new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder().setCustomId(`play:join:${sessionId}`).setLabel("Join game").setStyle(ButtonStyle.Success),
    new ButtonBuilder().setCustomId(`play:answer:${sessionId}`).setLabel("Answer").setStyle(ButtonStyle.Primary),
    new ButtonBuilder().setCustomId(`play:next:${sessionId}`).setLabel("Next round").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId(`play:leaderboard:${sessionId}`).setLabel("Leaderboard").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId(`play:finish:${sessionId}`).setLabel("Finish").setStyle(ButtonStyle.Danger),
  )];
  if (packMode !== "trivia") rows.push(new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder().setCustomId(`play:clue:${sessionId}`).setLabel("Reveal next clue").setStyle(ButtonStyle.Secondary),
  ));
  return rows;
}
function leaderboardLine(row: GameLeaderboardEntry, index: number): string {
  const label = row.team_name ? `${safeDisplay(row.team_name)} (${row.member_count} members)` : `<@${row.user_id ?? "unknown"}>`;
  return `${index + 1}. ${label} · ${row.score} points · ${row.correct} correct / ${row.answers} answered`;
}

export class PlayCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder()
    .setName("play")
    .setDescription("Create source-backed media games and play with your server")
    .addStringOption((option) => option.setName("action").setDescription("Game action").addChoices(
      { name: "Create question pack", value: "create-pack" },
      { name: "Add a question", value: "add-question" },
      { name: "Review pack", value: "review-pack" },
      { name: "Review question", value: "review-question" },
      { name: "Browse packs", value: "packs" },
      { name: "Start game", value: "start" },
      { name: "Join game", value: "join" },
      { name: "Submit answer", value: "answer" },
      { name: "Next round", value: "next" },
      { name: "Finish game", value: "finish" },
      { name: "Leaderboard", value: "leaderboard" },
      { name: "Edit question", value: "edit-question" },
      { name: "Question history", value: "question-history" },
    ))
    .addStringOption((option) => option.setName("pack_id").setDescription("Question pack ID"))
    .addStringOption((option) => option.setName("session_id").setDescription("Game session ID"))
    .addStringOption((option) => option.setName("question_id").setDescription("Question ID for edit or history"))
    .addStringOption((option) => option.setName("difficulty").setDescription("Question difficulty").addChoices({ name: "Easy", value: "easy" }, { name: "Standard", value: "standard" }, { name: "Hard", value: "hard" }, { name: "Expert", value: "expert" }))
    .addStringOption((option) => option.setName("title").setDescription("Pack title").setMaxLength(160))
    .addStringOption((option) => option.setName("description").setDescription("Pack description").setMaxLength(800))
    .addStringOption((option) => option.setName("mode").setDescription("Question mode").addChoices(
      { name: "Trivia", value: "trivia" },
      { name: "Guessing", value: "guessing" },
      { name: "Mystery", value: "mystery" },
    ))
    .addStringOption((option) => option.setName("question").setDescription("Question text").setMaxLength(500))
    .addStringOption((option) => option.setName("answer_text").setDescription("Your answer").setMaxLength(200))
    .addStringOption((option) => option.setName("correct_answer").setDescription("Correct answer").setMaxLength(200))
    .addStringOption((option) => option.setName("accepted_answers").setDescription("Accepted alternatives").setMaxLength(500))
    .addStringOption((option) => option.setName("source_url").setDescription("HTTPS source link").setMaxLength(1_000))
    .addStringOption((option) => option.setName("media_title").setDescription("Associated media title").setMaxLength(200))
    .addStringOption((option) => option.setName("clues").setDescription("Layered clues (category: clue, one per line)").setMaxLength(1_000))
    .addIntegerOption((option) => option.setName("rounds").setDescription("Number of rounds (1–10)").setMinValue(1).setMaxValue(10))
    .addStringOption((option) => option.setName("game_mode").setDescription("Scoring mode").addChoices({ name: "Individual", value: "individual" }, { name: "Competitive teams", value: "teams" }, { name: "Cooperative team", value: "cooperative" }))
    .addBooleanOption((option) => option.setName("approve").setDescription("Approve or reject pending content"));

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!interaction.guildId) {
      await interaction.reply({ content: "Media Games are available inside a Discord server.", flags: MessageFlags.Ephemeral });
      return;
    }
    const action = interaction.options.getString("action") ?? "home";
    try {
      switch (action) {
        case "home": await interaction.reply({ ...playHome(), flags: MessageFlags.Ephemeral }); return;
        case "create-pack": {
          const title = interaction.options.getString("title");
          if (!title) {
            await interaction.showModal(packModal());
            return;
          }
          await this.savePack(interaction, title, interaction.options.getString("description") ?? "", interaction.options.getString("mode") ?? "trivia");
          return;
        }
        case "add-question": {
          const packId = interaction.options.getString("pack_id");
          const question = interaction.options.getString("question");
          const answer = interaction.options.getString("correct_answer");
          const source = interaction.options.getString("source_url");
          if (!packId || !question || !answer || !source) {
            const modes = packId ? await query<{ mode: string }>("SELECT mode FROM community_quiz_packs WHERE id = $1 AND guild_id = $2", [packId, interaction.guildId]) : [];
            await interaction.showModal(questionModal(packId ?? "", modes[0]?.mode ?? "trivia"));
            return;
          }
          const id = await addQuizQuestion(
            interaction.guildId, packId, interaction.user.id, question, answer,
            (interaction.options.getString("accepted_answers") ?? "").split(",").map(value => value.trim()).filter(Boolean),
            source, interaction.options.getString("media_title") ?? undefined,
            [], interaction.options.getString("difficulty") ?? "standard",
            (interaction.options.getString("clues") ?? "").split(/\r?\n|\|/).map(value => value.trim()).filter(Boolean),
          );
          await interaction.reply({ content: `Question #${id} has been submitted for review. Source attribution is saved with it.`, flags: MessageFlags.Ephemeral });
          return;
        }
        case "review-pack": await this.reviewPackCommand(interaction); return;
        case "review-question": await this.reviewQuestionCommand(interaction); return;
        case "edit-question": {
          const questionId = interaction.options.getString("question_id");
          if (!questionId) throw new Error("Provide question_id to edit a question.");
          const question = await getQuizQuestionForEditing(interaction.guildId, questionId, interaction.user.id, isGuildManager(interaction));
          await interaction.showModal(editQuestionModal(question));
          return;
        }
        case "question-history": {
          const questionId = interaction.options.getString("question_id");
          if (!questionId) throw new Error("Provide question_id to view its history.");
          const history = await getQuizQuestionRevisionHistory(interaction.guildId, questionId, interaction.user.id, isGuildManager(interaction));
          const fields = history.revisions.slice(0, 8).map(revision => ({
            name: "Revision " + revision.revision + " · <t:" + Math.floor(new Date(revision.changed_at).getTime() / 1000) + ":R>",
            value: "**Question:** " + safeDisplay(revision.snapshot.question, 160) + "\n**Answer:** " + safeDisplay(revision.snapshot.correct_answer, 100) + "\n**Difficulty:** " + revision.snapshot.difficulty.toUpperCase(),
            inline: false,
          }));
          await interaction.reply({ embeds: [homeEmbed("Question revision history", "Current revision: " + history.currentRevision, fields.length ? fields : [{ name: "History", value: "No previous revisions.", inline: false }])], flags: MessageFlags.Ephemeral, allowedMentions: { parse: [] } });
          return;
        }
        case "packs": await this.showPacks(interaction); return;
        case "start": await this.start(interaction, interaction.options.getString("pack_id"), interaction.options.getInteger("rounds") ?? 5, (interaction.options.getString("game_mode") ?? "individual") as GameMode); return;
        case "join": await this.join(interaction, interaction.options.getString("session_id")); return;
        case "answer": await this.answerDirect(interaction); return;
        case "next": await this.advance(interaction, false); return;
        case "finish": await this.advance(interaction, true); return;
        case "leaderboard": await this.leaderboard(interaction); return;
        default: throw new Error("That game action is not available.");
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "The game action failed.";
      const issueHash = await createInteractionIssueLog(interaction, "/play", error);
      const response = issueHash ? `${message}\n\n${issueHashNotice(issueHash)}` : message;
      await interaction.reply({ content: response, flags: MessageFlags.Ephemeral }).catch(async () => {
        await interaction.followUp({ content: response, flags: MessageFlags.Ephemeral });
      });
    }
  }

  async handleButton(interaction: ButtonInteraction): Promise<boolean> {
    if (!interaction.guildId) return false;
    const [, action, sessionId] = interaction.customId.split(":");
    if (action === "create-pack") {
      await interaction.showModal(packModal());
      return true;
    }
    if (action === "add-question") {
      const packs = await listQuizPacks(interaction.guildId, "approved");
      if (!packs.length) {
        await interaction.reply({ content: "Create a question pack and have a moderator approve it before adding play-ready questions.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const select = new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(new StringSelectMenuBuilder()
        .setCustomId("play:question-pack")
        .setPlaceholder("Choose a question pack")
        .addOptions(packs.slice(0, 25).map((pack) => ({ label: pack.title.slice(0, 100), value: `${pack.id}:${pack.mode}` }))));
      await interaction.reply({ content: "Choose the pack for your new question.", components: [select], flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "start" || action === "start-team" || action === "start-coop") {
      const gameMode: GameMode = action === "start-team" ? "teams" : action === "start-coop" ? "cooperative" : "individual";
      const packs = await listQuizPacks(interaction.guildId, "approved");
      const available = packs.filter((pack) => pack.question_count > 0);
      if (!available.length) {
        await interaction.reply({ content: "No approved packs with approved questions are ready to play yet.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const select = new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(new StringSelectMenuBuilder()
        .setCustomId(`play:start-pack:${gameMode}`)
        .setPlaceholder("Choose a question pack")
        .addOptions(available.slice(0, 25).map((pack) => ({
          label: pack.title.slice(0, 100),
          value: pack.id,
          description: `${pack.question_count} approved questions`.slice(0, 100),
        }))));
      await interaction.reply({ content: "Choose an approved pack to start a multiplayer session in this channel.", components: [select], flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "packs") {
      await this.showPacks(interaction);
      return true;
    }
    if (action === "review") {
      await this.reviewQueue(interaction);
      return true;
    }
    if (action === "join" && sessionId) {
      await this.join(interaction, sessionId);
      return true;
    }
    if (action === "answer" && sessionId) {
      await interaction.showModal(answerModal(sessionId));
      return true;
    }
    if ((action === "next" || action === "finish") && sessionId) {
      await this.advanceFromButton(interaction, sessionId, action === "finish");
      return true;
    }
    if (action === "clue" && sessionId) {
      const session = await getGameSession(interaction.guildId, sessionId);
      if (!session) {
        await interaction.reply({ content: "That game session no longer exists.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const currentEmbed = interaction.message.embeds[0];
      if (!currentEmbed) {
        await interaction.reply({ content: "The current game question could not be loaded.", flags: MessageFlags.Ephemeral });
        return true;
      }
      try {
        const revealed = await revealGameClue(interaction.guildId, sessionId, interaction.user.id);
        const embed = EmbedBuilder.from(currentEmbed).addFields({
          name: "Clue " + revealed.number + " / " + revealed.total + " · " + revealed.clue.category.toUpperCase(),
          value: safeDisplay(revealed.clue.text, 200),
          inline: false,
        });
        await interaction.update({ embeds: [embed], components: gameButtons(sessionId, session.pack_mode) });
      } catch (error) {
        await interaction.reply({ content: error instanceof Error ? error.message : "The next clue could not be revealed.", flags: MessageFlags.Ephemeral });
      }
      return true;
    }
    if (action === "leaderboard" && sessionId) {
      await this.showLeaderboard(interaction, sessionId);
      return true;
    }
    if ((action === "approve-pack" || action === "reject-pack") && sessionId) {
      if (!isGuildManager(interaction)) {
        await interaction.reply({ content: "Manage Server permission is required to review game packs.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await reviewQuizPack(interaction.guildId, sessionId, action === "approve-pack");
      await interaction.reply({ content: action === "approve-pack" ? "Question pack approved." : "Question pack rejected.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if ((action === "approve-question" || action === "reject-question") && sessionId) {
      if (!isGuildManager(interaction)) {
        await interaction.reply({ content: "Manage Server permission is required to review questions.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await reviewQuizQuestion(interaction.guildId, sessionId, interaction.user.id, action === "approve-question");
      await interaction.reply({ content: action === "approve-question" ? "Question approved." : "Question rejected.", flags: MessageFlags.Ephemeral });
      return true;
    }
    return false;
  }

  async handleSelect(interaction: StringSelectMenuInteraction): Promise<boolean> {
    if (!interaction.guildId) return false;
    const [, action, gameMode] = interaction.customId.split(":");
    const selected = interaction.values[0];
    if (!selected) return false;
    if (action === "question-pack") {
      const [packId, packMode] = selected.split(":");
      await interaction.showModal(questionModal(packId, packMode ?? "trivia"));
      return true;
    }
    if (action === "start-pack") {
      await this.start(interaction, selected, 5, gameMode === "teams" || gameMode === "cooperative" ? gameMode : "individual");
      return true;
    }
    return false;
  }

  async handleModal(interaction: ModalSubmitInteraction): Promise<boolean> {
    if (!interaction.guildId) return false;
    const [prefix, action, sessionId] = interaction.customId.split(":");
    if (prefix !== "play") return false;
    try {
      if (action === "create-pack") {
        await this.savePack(
          interaction,
          interaction.fields.getTextInputValue("title"),
          interaction.fields.getTextInputValue("description"),
          interaction.fields.getTextInputValue("mode"),
        );
        return true;
      }
      if (action === "add-question" && sessionId) {
        const packId = sessionId === "select" ? interaction.fields.getTextInputValue("pack_id").trim() : sessionId;
        const source = interaction.fields.getTextInputValue("source");
        if (!isValidHttpsUrl(source, true)) throw new Error("A valid HTTPS source is required.");
        const accepted = interaction.fields.getTextInputValue("accepted").split(/\r?\n|\|/).map(value => value.trim()).filter(Boolean);
        const id = await addQuizQuestion(interaction.guildId, packId, interaction.user.id,
          interaction.fields.getTextInputValue("question"), interaction.fields.getTextInputValue("answer"),
          accepted, source, undefined, [], sessionId === "select" ? "standard" : interaction.fields.getTextInputValue("difficulty"));
        await interaction.reply({ content: `Question #${id} was submitted for review.`, flags: MessageFlags.Ephemeral });
        return true;
      }
      if (action === "edit-question" && sessionId) {
        const revision = await editQuizQuestion(interaction.guildId, sessionId, interaction.user.id, isGuildManager(interaction),
          interaction.fields.getTextInputValue("question"), interaction.fields.getTextInputValue("answer"),
          interaction.fields.getTextInputValue("accepted").split(","), interaction.fields.getTextInputValue("source"),
          interaction.fields.getTextInputValue("difficulty"));
        await interaction.reply({ content: `Question #${sessionId} was saved as revision ${revision} and returned to moderator review.`, flags: MessageFlags.Ephemeral });
        return true;
      }      if (action === "answer" && sessionId) {
        const result = await answerGameQuestion(
          interaction.guildId,
          sessionId,
          interaction.user.id,
          interaction.fields.getTextInputValue("answer"),
        );
        await interaction.reply({
          content: result.correct
            ? `${emoji.check} Correct — round ${result.round}/${result.total}. The source is [here](${result.sourceUrl}).`
            : `Not quite — round ${result.round}/${result.total}. The answer will be revealed when the host closes this round. [Source](${result.sourceUrl}).`,
          flags: MessageFlags.Ephemeral,
        });
        return true;
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "The game action failed.";
      const issueHash = await createInteractionIssueLog(interaction, "/play", error, { action: "modal-submit" });
      await interaction.reply({ content: issueHash ? `${message}\n\n${issueHashNotice(issueHash)}` : message, flags: MessageFlags.Ephemeral });
      return true;
    }
    return false;
  }

  private async savePack(
    interaction: ChatInputCommandInteraction | ModalSubmitInteraction,
    title: string,
    description: string,
    mode: string,
  ): Promise<void> {
    if (!["trivia", "guessing", "mystery"].includes(mode.trim().toLowerCase())) {
      throw new Error("Choose trivia, guessing or mystery as the pack mode.");
    }
    const id = await createQuizPack(
      interaction.guildId!,
      interaction.user.id,
      title,
      description,
      mode.trim().toLowerCase() as "trivia" | "guessing" | "mystery",
    );
    await interaction.reply({ content: `Question pack #${id} is pending moderator review. Once approved, add source-backed questions to it.`, flags: MessageFlags.Ephemeral });
  }

  private async showPacks(interaction: ChatInputCommandInteraction | ButtonInteraction): Promise<void> {
    const packs = await listQuizPacks(interaction.guildId!, "approved");
    if (!packs.length) {
      await interaction.reply({ content: "There are no approved question packs yet.", flags: MessageFlags.Ephemeral });
      return;
    }
    await interaction.reply({
      embeds: [homeEmbed("Approved question packs", "Only approved source-backed questions can enter active games.", packs.map((pack) => ({
        name: `#${pack.id} · ${safeDisplay(pack.title)}`,
        value: `${pack.question_count} approved question(s)\n${safeDisplay(pack.description, 200) || "No description"}`,
        inline: false,
      })))],
      flags: MessageFlags.Ephemeral,
    });
  }

  private async reviewQueue(interaction: ButtonInteraction): Promise<void> {
    if (!interaction.guildId || !isGuildManager(interaction)) {
      await interaction.reply({ content: "Manage Server permission is required to review question packs.", flags: MessageFlags.Ephemeral });
      return;
    }
    const [packs, questions] = await Promise.all([
      query<{ id: string; title: string; description: string }>(
        "SELECT id, title, description FROM community_quiz_packs WHERE guild_id = $1 AND status = 'pending' ORDER BY created_at ASC LIMIT 5",
        [interaction.guildId],
      ),
      pendingQuizQuestions(interaction.guildId),
    ]);
    const firstPack = packs[0];
    const firstQuestion = questions[0];
    const components: ActionRowBuilder<ButtonBuilder>[] = [];
    if (firstPack) {
      components.push(new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId(`play:approve-pack:${firstPack.id}`).setLabel(`Approve pack #${firstPack.id}`).setStyle(ButtonStyle.Success),
        new ButtonBuilder().setCustomId(`play:reject-pack:${firstPack.id}`).setLabel("Reject pack").setStyle(ButtonStyle.Danger),
      ));
    }
    if (firstQuestion) {
      components.push(new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId(`play:approve-question:${firstQuestion.id}`).setLabel(`Approve question #${firstQuestion.id}`).setStyle(ButtonStyle.Success),
        new ButtonBuilder().setCustomId(`play:reject-question:${firstQuestion.id}`).setLabel("Reject question").setStyle(ButtonStyle.Danger),
      ));
    }
    const fields = [
      ...packs.map((pack) => ({ name: `Pack #${pack.id} · ${safeDisplay(pack.title)}`, value: safeDisplay(pack.description, 150), inline: false })),
      ...questions.map((question) => ({ name: `Question #${question.id} · ${safeDisplay(question.title)}`, value: `${safeDisplay(question.question, 250)}\n[Source](${question.source_url})`, inline: false })),
    ];
    await interaction.reply({
      embeds: [homeEmbed("Game review queue", fields.length ? "Source-backed submissions awaiting review." : "There are no pending game submissions.", fields)],
      components,
      flags: MessageFlags.Ephemeral,
      allowedMentions: { parse: [] },
    });
  }

  private async reviewPackCommand(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!isGuildManager(interaction)) throw new Error("Manage Server permission is required.");
    const id = interaction.options.getString("pack_id");
    const approve = interaction.options.getBoolean("approve");
    if (!id || approve === null) throw new Error("Provide pack_id and approve true/false.");
    await reviewQuizPack(interaction.guildId!, id, approve);
    await interaction.reply({ content: approve ? "Question pack approved." : "Question pack rejected.", flags: MessageFlags.Ephemeral });
  }

  private async reviewQuestionCommand(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!isGuildManager(interaction)) throw new Error("Manage Server permission is required.");
    const id = interaction.options.getString("session_id");
    const approve = interaction.options.getBoolean("approve");
    if (!id || approve === null) throw new Error("Provide the question ID in session_id and approve true/false.");
    await reviewQuizQuestion(interaction.guildId!, id, interaction.user.id, approve);
    await interaction.reply({ content: approve ? "Question approved." : "Question rejected.", flags: MessageFlags.Ephemeral });
  }

  private async start(
    interaction: ChatInputCommandInteraction | StringSelectMenuInteraction,
    packId: string | null,
    rounds: number,
    gameMode: GameMode = "individual",
  ): Promise<void> {
    if (!packId) {
      await interaction.reply({ content: "Choose an approved pack using the game panel or provide pack_id.", flags: MessageFlags.Ephemeral });
      return;
    }
    const session = await startGame(interaction.guildId!, interaction.channelId, interaction.user.id, packId, rounds, gameMode);
    const question = await getCurrentGameQuestion(interaction.guildId!, session.id);
    if (!question) throw new Error("The first approved question could not be loaded.");
    const channel = interaction.channel;
    if (!channel?.isTextBased() || !("send" in channel)) {
      throw new Error("Start the game from a text channel so the server can participate.");
    }
    const message = await (channel as TextChannel).send({
      embeds: [questionEmbed(`${emoji.game} ${session.title}${session.game_mode === "teams" ? " · Team battle" : session.game_mode === "cooperative" ? " · Co-op" : ""}`, question.question, question.source_url, 1, session.question_ids.length, question.difficulty)],
      components: gameButtons(session.id, session.pack_mode),
      allowedMentions: { parse: [] },
    });
    await query("UPDATE community_game_sessions SET message_id = $1 WHERE id = $2 AND guild_id = $3", [message.id, session.id, interaction.guildId]);
    const notice = session.game_mode === "teams" ? " Players are balanced between Team A and Team B when they join." : session.game_mode === "cooperative" ? " Everyone contributes to the Community Team score." : "";
    await interaction.reply({ content: `Game session #${session.id} started.${notice} Share the channel message with your players.`, flags: MessageFlags.Ephemeral });
  }

  private async join(
    interaction: ChatInputCommandInteraction | ButtonInteraction,
    sessionId: string | null,
  ): Promise<void> {
    if (!sessionId) throw new Error("Provide session_id or use Join game on the game message.");
    const teamName = await joinGame(interaction.guildId!, sessionId, interaction.user.id);
    await interaction.reply({ content: teamName ? `You joined ${teamName}. Your answers contribute to the team score.` : "You joined the game. Submit one answer for each round.", flags: MessageFlags.Ephemeral });
  }

  private async answerDirect(interaction: ChatInputCommandInteraction): Promise<void> {
    const sessionId = interaction.options.getString("session_id");
    const answer = interaction.options.getString("answer_text");
    if (!sessionId || !answer) throw new Error("Provide session_id and answer_text, or use the Answer button.");
    const result = await answerGameQuestion(interaction.guildId!, sessionId, interaction.user.id, answer);
    await interaction.reply({
      content: result.correct ? `${emoji.check} Correct. Round ${result.round}/${result.total}.${result.teamName ? ` ${result.teamName} gains 100 points.` : ""} [Source](${result.sourceUrl}).` : `Not quite. The round answer is revealed after the host advances.${result.teamName ? ` Your answer was recorded for ${result.teamName}.` : ""} [Source](${result.sourceUrl}).`,
      flags: MessageFlags.Ephemeral,
    });
  }

  private async advance(interaction: ChatInputCommandInteraction, finish: boolean): Promise<void> {
    const sessionId = interaction.options.getString("session_id");
    if (!sessionId) throw new Error("Provide session_id.");
    const session = await getGameSession(interaction.guildId!, sessionId);
    if (!session) throw new Error("That game session was not found.");
    if (session.host_id !== interaction.user.id) throw new Error("Only the host can advance or finish the game.");
    const current = await getCurrentGameQuestion(interaction.guildId!, sessionId);
    const result = await advanceGame(interaction.guildId!, sessionId, interaction.user.id, finish);
    const leaderboard = result.finished ? await getGameLeaderboard(interaction.guildId!, sessionId) : [];
    await interaction.reply({
      embeds: [homeEmbed(result.finished ? "Game finished" : "Round advanced", [
        current ? `Previous answer: **${safeDisplay(current.correct_answer)}**\n[Source](${current.source_url})` : "",
        result.finished ? leaderboard.map((row, index) => leaderboardLine(row, index)).join("\n") : `Next round: ${result.round}/${result.total}`,
      ].filter(Boolean).join("\n\n"))],
      flags: MessageFlags.Ephemeral,
    });
  }

  private async advanceFromButton(interaction: ButtonInteraction, sessionId: string, finish: boolean): Promise<void> {
    const session = await getGameSession(interaction.guildId!, sessionId);
    if (!session) {
      await interaction.reply({ content: "That game session no longer exists.", flags: MessageFlags.Ephemeral });
      return;
    }
    if (session.host_id !== interaction.user.id) {
      await interaction.reply({ content: "Only the game host can advance rounds or finish the game.", flags: MessageFlags.Ephemeral });
      return;
    }
    const current = await getCurrentGameQuestion(interaction.guildId!, sessionId);
    const result = await advanceGame(interaction.guildId!, sessionId, interaction.user.id, finish);
    if (result.finished) {
      const leaderboard = await getGameLeaderboard(interaction.guildId!, sessionId);
      const embed = homeEmbed("Game finished", [
        current ? `Final answer: **${safeDisplay(current.correct_answer)}** · [Source](${current.source_url})` : "",
        leaderboard.map((row, index) => leaderboardLine(row, index)).join("\n") || "No answers were submitted.",
      ].filter(Boolean).join("\n\n"));
      await interaction.update({ embeds: [embed], components: [] });
      return;
    }
    const nextQuestion = await getCurrentGameQuestion(interaction.guildId!, sessionId);
    if (!nextQuestion) {
      await interaction.update({ embeds: [homeEmbed("Game finished", "There are no more approved questions in this session.")], components: [] });
      return;
    }
    await interaction.update({
      embeds: [questionEmbed(
        `${emoji.game} ${session.title} · Previous answer: ${current?.correct_answer ?? "unavailable"}`,
        nextQuestion.question,
        nextQuestion.source_url,
        result.round,
        result.total,
        nextQuestion.difficulty,
      )],
      components: gameButtons(sessionId, session.pack_mode),
    });
  }

  private async leaderboard(interaction: ChatInputCommandInteraction): Promise<void> {
    const sessionId = interaction.options.getString("session_id");
    if (!sessionId) throw new Error("Provide session_id.");
    await this.showLeaderboard(interaction, sessionId);
  }

  private async showLeaderboard(interaction: ButtonInteraction | ChatInputCommandInteraction, sessionId: string): Promise<void> {
    const rows = await getGameLeaderboard(interaction.guildId!, sessionId);
    await interaction.reply({
      embeds: [homeEmbed(rows.some(row => row.team_name) ? "Team leaderboard" : "Game leaderboard", "Fixed scoring: 100 points for a correct answer, zero for an incorrect answer. Ties use correct answers and then stable team or player order.", rows.map((row, index) => ({
        name: leaderboardLine(row, index).split(" · ")[0] ?? "Player",
        value: leaderboardLine(row, index).split(" · ").slice(1).join(" · ") || "No answers yet",
        inline: false,
      })))],
      flags: MessageFlags.Ephemeral,
      allowedMentions: { parse: [] },
    });
  }
}
