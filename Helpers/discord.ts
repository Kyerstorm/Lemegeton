import { ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder, type APIEmbedField } from "discord.js";
export const COLOUR=0x5865f2;
export function homeEmbed(title:string,description:string,fields:APIEmbedField[]=[]):EmbedBuilder{
 return new EmbedBuilder().setColor(COLOUR).setTitle(title.slice(0,256)).setDescription(description.slice(0,4000)).addFields(fields.slice(0,25)).setFooter({text:"Lemegeton · Community media platform"});
}

export function navigationButtons(prefix:string,choices:Array<{id:string;label:string;style?:ButtonStyle}>):ActionRowBuilder<ButtonBuilder>{
 const row=new ActionRowBuilder<ButtonBuilder>();
 for(const choice of choices.slice(0,5)){
  row.addComponents(new ButtonBuilder().setCustomId(`${prefix}:${choice.id}`).setLabel(choice.label.slice(0,80)).setStyle(choice.style??ButtonStyle.Secondary));
 }
 return row;
}
