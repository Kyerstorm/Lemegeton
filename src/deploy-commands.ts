import {ApplicationIntegrationType,InteractionContextType,REST,Routes} from "discord.js";
import {loadConfig} from "../helpers/runtime/config.js";
import {configureLogger,logger} from "../helpers/runtime/logger.js";
import {createCommandRegistry} from "./registry.js";

const MODERATOR_COMMANDS=new Set(["log","moderators","planned","adminlogin","convertlinks"]);

async function deploy():Promise<void>{
 const config=loadConfig();
 configureLogger(config.logLevel);
 const commands=createCommandRegistry(config);
 const rest=new REST({version:"10"}).setToken(config.discordToken);
 const globalCommands=commands
  .filter(command=>!MODERATOR_COMMANDS.has(command.data.name))
  .map(command=>({
   ...command.data.toJSON(),
   contexts:[InteractionContextType.Guild],
   integration_types:[ApplicationIntegrationType.GuildInstall],
  }));
 await rest.put(Routes.applicationCommands(config.applicationId),{body:globalCommands});

 const moderatorCommands=commands
  .filter(command=>MODERATOR_COMMANDS.has(command.data.name))
  .map(command=>command.data.toJSON());
 if(config.botModeratorGuildId){
  await rest.put(Routes.applicationGuildCommands(config.applicationId,config.botModeratorGuildId),{body:moderatorCommands});
  logger.info("Deployed bot-moderator commands to their dedicated server",{guildId:config.botModeratorGuildId,names:moderatorCommands.map(command=>command.name)});
 }else{
  logger.warn("Bot-moderator commands were not registered; BOT_MODERATOR_GUILD_ID is not configured.");
 }
 logger.info("Deployed server-only Lemegeton feature commands",{names:globalCommands.map(command=>command.name)});
}
void deploy().catch(error=>{
 logger.error("Slash command deployment failed",{reason:error instanceof Error?error.message:"Unknown error"});
 process.exitCode=1;
});
