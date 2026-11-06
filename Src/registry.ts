import type {BotConfig} from "../Helpers/config.js";
import type {FeatureCommand} from "../Helpers/command.js";
import {DiscoverCommand} from "./discover.js";
import {ArchiveCommand} from "./archive.js";
import {CommunityCommand} from "./community.js";
import {PlayCommand} from "./play.js";
import {ProfileCommand} from "./profile.js";
import {SettingsCommand} from "./settings.js";
import {CustomRoleCommand} from "./custom-role.js";
export function createCommandRegistry(config:BotConfig):FeatureCommand[]{
 const commands:FeatureCommand[]=[new DiscoverCommand(config),new ArchiveCommand(),new CommunityCommand(config),new PlayCommand(),new ProfileCommand(config),new CustomRoleCommand(),new SettingsCommand()];
 const names=new Set<string>();for(const command of commands){if(names.has(command.data.name))throw new Error(`Duplicate feature command: /${command.data.name}`);names.add(command.data.name);}return commands;
}
