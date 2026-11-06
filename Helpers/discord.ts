import { EmbedBuilder, type APIEmbedField } from "discord.js";
export const COLOUR=0x5865f2;
export function homeEmbed(title:string,description:string,fields:APIEmbedField[]=[]):EmbedBuilder{
 return new EmbedBuilder().setColor(COLOUR).setTitle(title.slice(0,256)).setDescription(description.slice(0,4000)).addFields(fields.slice(0,25)).setFooter({text:"Lemegeton · Community media platform"});
}
