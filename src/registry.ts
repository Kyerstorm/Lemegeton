import type {BotConfig} from "../helpers/runtime/config.js";
import type {FeatureCommand} from "../helpers/commands/command.js";
import {DiscoverCommand} from "./commands/discover.js";
import {ArchiveCommand} from "./commands/archive.js";
import {CommunityCommand} from "./commands/community.js";
import {PlayCommand} from "./commands/play.js";
import {ProfileCommand} from "./commands/profile.js";
import {SettingsCommand} from "./commands/settings.js";
import {CustomRoleCommand} from "./commands/custom-role.js";
import {HelpCommand} from "./standalone/help.js";
import {PrivacyCommand} from "./standalone/privacy.js";
import {FeedbackCommand} from "./standalone/feedback.js";
import {LogCommand} from "./standalone/log.js";
import {PlannedCommand} from "./utility/planned.js";
import {BotModeratorsCommand} from "./standalone/moderators.js";
import {TimestampCommand} from "./utility/timestamp.js";
import {InviteCommand} from "./utility/invite.js";
import {ConvertLinksCommand} from "./utility/convertlinks.js";
import {AdminLoginCommand} from "./standalone/admin-login.js";

export function createCommandRegistry(config:BotConfig):FeatureCommand[]{
 const commands:FeatureCommand[]=[
  new DiscoverCommand(config),new ArchiveCommand(),new CommunityCommand(config),
  new PlayCommand(),new ProfileCommand(config),new CustomRoleCommand(),new SettingsCommand(),
  new HelpCommand(),new PrivacyCommand(),new FeedbackCommand(),new LogCommand(config.botModeratorGuildId),new PlannedCommand(config.botModeratorGuildId),new BotModeratorsCommand(config.botModeratorGuildId),new TimestampCommand(),new InviteCommand(config),new ConvertLinksCommand(config),new AdminLoginCommand(config),
 ];
 const names=new Set<string>();
 for(const command of commands){
  if(names.has(command.data.name))throw new Error(`Duplicate command: /${command.data.name}`);
  names.add(command.data.name);
 }
 return commands;
}
