import type {BotConfig} from "../helpers/runtime/config.js";
import type {FeatureCommand} from "../helpers/commands/command.js";
import {DiscoverCommand} from "./commands/discover.js";
import {ArchiveCommand} from "./commands/archive.js";
import {CommunityCommand} from "./commands/community.js";
import {PlayCommand} from "./commands/play.js";
import {ProfileCommand} from "./commands/profile.js";
import {SettingsCommand} from "./commands/settings.js";
import {CustomRoleCommand} from "./commands/custom-role.js";
import {MusicCommand} from "./commands/music.js";
import {TimelineCommand} from "./commands/timeline.js";
import {IndustryCommand} from "./commands/industry.js";
import {IdentifyCommand} from "./commands/identify.js";
import {ExchangeCommand} from "./commands/exchange.js";
import {RelayCommand} from "./commands/relay.js";
import {WorkshopCommand} from "./commands/workshop.js";
import {CapsuleCommand} from "./commands/capsule.js";
import {CouncilCommand} from "./commands/council.js";
import {ExpeditionCommand} from "./commands/expedition.js";
import {CasebookCommand} from "./commands/casebook.js";
import {LanguageCommand} from "./commands/language.js";
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
import {GitHubCommand} from "./standalone/github.js";

export function createCommandRegistry(config:BotConfig):FeatureCommand[]{
 const commands:FeatureCommand[]=[
  new DiscoverCommand(config),new TimelineCommand(config),new IndustryCommand(config),new IdentifyCommand(config),new ExchangeCommand(config),new RelayCommand(),new WorkshopCommand(),new CapsuleCommand(),new CouncilCommand(),new ExpeditionCommand(config),new CasebookCommand(config),new ArchiveCommand(),new CommunityCommand(config),
  new PlayCommand(),new ProfileCommand(config),new CustomRoleCommand(),new SettingsCommand(config),new MusicCommand(config),new LanguageCommand(),
  new HelpCommand(),new PrivacyCommand(),new FeedbackCommand(config.botFeedbackChannelId),new LogCommand(config.botModeratorGuildId,config.adminDiscordId),new PlannedCommand(config.botModeratorGuildId),new BotModeratorsCommand(config.botModeratorGuildId,config.adminDiscordId),new TimestampCommand(),new InviteCommand(config),new ConvertLinksCommand(config),new AdminLoginCommand(config),new GitHubCommand(config),
 ];
 const names=new Set<string>();
 for(const command of commands){
  if(names.has(command.data.name))throw new Error(`Duplicate command: /${command.data.name}`);
  names.add(command.data.name);
 }
 return commands;
}
