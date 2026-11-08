import {ApplicationIntegrationType,InteractionContextType,REST,Routes} from "discord.js";
import {loadConfig} from "../helpers/config.js";
import {configureLogger,logger} from "../helpers/logger.js";
import {createCommandRegistry} from "./registry.js";

async function deploy():Promise<void>{
 const config=loadConfig();
 configureLogger(config.logLevel);
 const commands=createCommandRegistry(config).map(command=>({
  ...command.data.toJSON(),
  contexts:[InteractionContextType.Guild],
  integration_types:[ApplicationIntegrationType.GuildInstall],
 }));
 const rest=new REST({version:"10"}).setToken(config.discordToken);
 await rest.put(Routes.applicationCommands(config.applicationId),{body:commands});
 logger.info("Deployed server-only Lemegeton commands",{names:commands.map(command=>command.name)});
}
void deploy().catch(error=>{
 logger.error("Slash command deployment failed",{reason:error instanceof Error?error.message:"Unknown error"});
 process.exitCode=1;
});
