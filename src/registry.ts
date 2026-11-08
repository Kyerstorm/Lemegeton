import type {BotConfig} from "../helpers/config.js";
import type {FeatureCommand} from "../helpers/command.js";
import {DiscoverCommand} from "./discover.js";
import {ArchiveCommand} from "./archive.js";
import {CommunityCommand} from "./community.js";
import {PlayCommand} from "./play.js";
import {ProfileCommand} from "./profile.js";
import {SettingsCommand} from "./settings.js";
import {CustomRoleCommand} from "./custom-role.js";
import {HelpCommand} from "./help.js";
import {PrivacyCommand} from "./privacy.js";
import {FeedbackCommand} from "./feedback.js";
import {LogCommand} from "./log.js";
import {PlannedCommand} from "./planned.js";
import {BotModeratorsCommand} from "./moderators.js";
import {TimestampCommand} from "./timestamp.js";
import {InviteCommand} from "./invite.js";
import {ConvertLinksCommand} from "./convertlinks.js";

export function createCommandRegistry(config:BotConfig):FeatureCommand[]{
 const commands:FeatureCommand[]=[
  new DiscoverCommand(config),new ArchiveCommand(),new CommunityCommand(config),
  new PlayCommand(),new ProfileCommand(config),new CustomRoleCommand(),new SettingsCommand(),
  new HelpCommand(),new PrivacyCommand(),new FeedbackCommand(),new LogCommand(),new PlannedCommand(),new BotModeratorsCommand(),new TimestampCommand(),new InviteCommand(config),new ConvertLinksCommand(config),
 ];
 const names=new Set<string>();
 for(const command of commands){
  if(names.has(command.data.name))throw new Error(`Duplicate command: /${command.data.name}`);
  names.add(command.data.name);
 }
 return commands;
}
