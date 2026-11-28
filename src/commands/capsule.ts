import {
  ActionRowBuilder,ButtonBuilder,ButtonStyle,EmbedBuilder,MessageFlags,ModalBuilder,
  SlashCommandBuilder,StringSelectMenuBuilder,TextInputBuilder,TextInputStyle,
  type ButtonInteraction,type ChatInputCommandInteraction,type ModalSubmitInteraction,
  type StringSelectMenuInteraction,
} from "discord.js";
import type {FeatureCommand} from "../../helpers/commands/command.js";
import {EMBED_COLOURS} from "../../helpers/embeds/core.js";
import {
  cancelTimeCapsule,contributeToTimeCapsule,createTimeCapsule,getTimeCapsule,
  listTimeCapsules,sealTimeCapsule,
} from "../../helpers/community/time-capsules.js";

function capsuleModal(customId:string,title:string,fields:Array<{id:string;label:string;paragraph?:boolean;required?:boolean;max?:number}>):ModalBuilder{
  const result=new ModalBuilder().setCustomId(customId).setTitle(title.slice(0,45));
  for(const field of fields.slice(0,5)){
    result.addComponents(new ActionRowBuilder<TextInputBuilder>().addComponents(
      new TextInputBuilder().setCustomId(field.id).setLabel(field.label.slice(0,45))
        .setStyle(field.paragraph?TextInputStyle.Paragraph:TextInputStyle.Short)
        .setMaxLength(field.max??200).setRequired(field.required??false).setPlaceholder("Optional"),
    ));
  }
  return result;
}

function formatDate(value:string):string{
  const timestamp=Math.floor(new Date(value).getTime()/1_000);
  return Number.isFinite(timestamp)?"<t:"+timestamp+":F>":"Unknown";
}

export class CapsuleCommand implements FeatureCommand{
  readonly data=new SlashCommandBuilder().setName("capsule")
    .setDescription("Collect a shared message and reveal it to its chosen audience at a scheduled time.");

  async execute(interaction:ChatInputCommandInteraction):Promise<void>{
    if(!interaction.guildId){await interaction.reply({content:"Time capsules are available inside a server.",flags:MessageFlags.Ephemeral});return;}
    if(!interaction.channel?.isTextBased()||!("send" in interaction.channel)){
      await interaction.reply({content:"Open /capsule in a text channel where the bot can send the scheduled reveal.",flags:MessageFlags.Ephemeral});return;
    }
    await interaction.reply({...this.homePayload(),flags:MessageFlags.Ephemeral});
  }

  async handleButton(interaction:ButtonInteraction):Promise<boolean>{
    if(!interaction.customId.startsWith("capsule:"))return false;
    const [,action,capsuleId]=interaction.customId.split(":");
    if(!interaction.guildId){await interaction.reply({content:"Time capsules are available inside a server.",flags:MessageFlags.Ephemeral});return true;}
    if(action==="home"){await interaction.update(this.homePayload());return true;}
    if(action==="create"){
      if(!interaction.channelId||!interaction.channel?.isTextBased()||!("send" in interaction.channel)){
        await interaction.reply({content:"Create capsules from a text channel where the bot can send the reveal.",flags:MessageFlags.Ephemeral});return true;
      }
      await interaction.showModal(capsuleModal("capsule:create-submit:"+interaction.channelId,"Create a time capsule",[
        {id:"title",label:"Capsule title",required:true,max:180},
        {id:"description",label:"Message for the reveal",paragraph:true,max:800},
        {id:"release",label:"Release time (ISO, e.g. 2027-01-05T12:30Z)",required:true,max:30},
        {id:"audience",label:"Audience: guild, contributors or owner",max:20},
      ]));
      return true;
    }
    if(action==="browse"){
      await interaction.deferUpdate();await interaction.editReply(await this.browsePayload(interaction.guildId,interaction.user.id));return true;
    }
    if(!capsuleId)return false;
    const item=await getTimeCapsule(interaction.guildId,capsuleId,interaction.user.id);
    if(!item){await interaction.reply({content:"That capsule was not found in this server.",flags:MessageFlags.Ephemeral});return true;}
    if(action==="view"){await interaction.update(this.detailPayload(item,interaction.user.id));return true;}
    if(action==="contribute"){
      if(item.capsule.status!=="collecting"){await interaction.reply({content:"This capsule is sealed and no longer accepts contributions.",flags:MessageFlags.Ephemeral});return true;}
      await interaction.showModal(capsuleModal("capsule:contribute-submit:"+capsuleId,"Add your capsule contribution",[
        {id:"content",label:"Your message",required:true,paragraph:true,max:2_500},
      ]));
      return true;
    }
    if(action==="seal"||action==="cancel"){
      try{
        if(action==="seal")await sealTimeCapsule({guildId:interaction.guildId,capsuleId,ownerId:interaction.user.id});
        else await cancelTimeCapsule({guildId:interaction.guildId,capsuleId,ownerId:interaction.user.id});
        const updated=await getTimeCapsule(interaction.guildId,capsuleId,interaction.user.id);
        await interaction.update(updated?this.detailPayload(updated,interaction.user.id):this.homePayload());
      }catch(error){await interaction.reply({content:error instanceof Error?error.message:"The capsule could not be updated.",flags:MessageFlags.Ephemeral});}
      return true;
    }
    return false;
  }

  async handleSelect(interaction:StringSelectMenuInteraction):Promise<boolean>{
    if(!interaction.customId.startsWith("capsule:"))return false;
    if(!interaction.guildId){await interaction.reply({content:"Time capsules are available inside a server.",flags:MessageFlags.Ephemeral});return true;}
    if(interaction.customId==="capsule:list"){
      const id=interaction.values[0];
      const item=id?await getTimeCapsule(interaction.guildId,id,interaction.user.id):null;
      if(!item){await interaction.reply({content:"That capsule is no longer available.",flags:MessageFlags.Ephemeral});return true;}
      await interaction.update(this.detailPayload(item,interaction.user.id));return true;
    }
    return false;
  }

  async handleModal(interaction:ModalSubmitInteraction):Promise<boolean>{
    if(!interaction.customId.startsWith("capsule:"))return false;
    if(!interaction.guildId){await interaction.reply({content:"Time capsules are available inside a server.",flags:MessageFlags.Ephemeral});return true;}
    try{
      const [,action,id]=interaction.customId.split(":");
      if(action==="create-submit"&&id){
        const rawAudience=interaction.fields.getTextInputValue("audience").trim().toLowerCase();
        if(rawAudience&&rawAudience!=="guild"&&rawAudience!=="contributors"&&rawAudience!=="owner"){
          await interaction.reply({content:"Audience must be guild, contributors or owner.",flags:MessageFlags.Ephemeral});return true;
        }
        const capsuleId=await createTimeCapsule({
          guildId:interaction.guildId,ownerId:interaction.user.id,channelId:id,
          title:interaction.fields.getTextInputValue("title"),
          description:interaction.fields.getTextInputValue("description"),
          releaseAt:interaction.fields.getTextInputValue("release"),
          audience:(rawAudience||"guild") as "guild"|"contributors"|"owner",
        });
        await interaction.reply({
          content:"Time capsule **#"+capsuleId+"** created. Contributions remain editable until the owner seals it.",
          components:[new ActionRowBuilder<ButtonBuilder>().addComponents(
            new ButtonBuilder().setCustomId("capsule:view:"+capsuleId).setLabel("Open capsule").setStyle(ButtonStyle.Primary),
          )],
          flags:MessageFlags.Ephemeral,
        });return true;
      }
      if(action==="contribute-submit"&&id){
        await contributeToTimeCapsule({
          guildId:interaction.guildId,capsuleId:id,contributorId:interaction.user.id,
          content:interaction.fields.getTextInputValue("content"),
        });
        await interaction.reply({
          content:"Your capsule contribution was saved. You can update it until the capsule is sealed.",
          components:[new ActionRowBuilder<ButtonBuilder>().addComponents(
            new ButtonBuilder().setCustomId("capsule:view:"+id).setLabel("Open capsule").setStyle(ButtonStyle.Primary),
          )],
          flags:MessageFlags.Ephemeral,
        });return true;
      }
    }catch(error){await interaction.reply({content:error instanceof Error?error.message:"The capsule action could not be completed.",flags:MessageFlags.Ephemeral});return true;}
    return false;
  }

  private homePayload(){
    const embed=new EmbedBuilder().setColor(EMBED_COLOURS.primary).setTitle("Time capsules")
      .setDescription("Collect messages from the community, seal the capsule and reveal it at a chosen date. Text contributions only; scheduled delivery depends on the bot being online and having access to the destination or recipients. The stored content is not cryptographically encrypted.");
    return {embeds:[embed],components:[new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("capsule:create").setLabel("Create capsule").setStyle(ButtonStyle.Primary),
      new ButtonBuilder().setCustomId("capsule:browse").setLabel("Browse capsules").setStyle(ButtonStyle.Secondary),
    )]};
  }

  private async browsePayload(guildId:string,viewerId:string){
    const capsules=await listTimeCapsules(guildId,15,viewerId);
    const embed=new EmbedBuilder().setColor(EMBED_COLOURS.primary).setTitle("Server time capsules")
      .setDescription(capsules.map(item=>"**#"+item.id+" · "+item.title+"**\n"+item.status+" · "+item.contribution_count+" contribution(s) · "+formatDate(item.release_at)).join("\n\n").slice(0,3_900)
        ||"This server has no collecting or sealed capsules.");
    if(!capsules.length)return {embeds:[embed],components:[new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("capsule:home").setLabel("Back").setStyle(ButtonStyle.Secondary),
    )]};
    const select=new StringSelectMenuBuilder().setCustomId("capsule:list").setPlaceholder("Open a capsule")
      .addOptions(capsules.map(item=>({label:("#"+item.id+" · "+item.title).slice(0,100),value:item.id,description:item.status+" · "+item.contribution_count+" contributions"})));
    return {embeds:[embed],components:[
      new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(select),
      new ActionRowBuilder<ButtonBuilder>().addComponents(new ButtonBuilder().setCustomId("capsule:home").setLabel("Back").setStyle(ButtonStyle.Secondary)),
    ]};
  }

  private detailPayload(item:NonNullable<Awaited<ReturnType<typeof getTimeCapsule>>>,viewerId:string){
    const capsule=item.capsule;
    const isOwner=capsule.owner_id===viewerId;
    const isContributor=item.contributions.some(contribution=>contribution.contributor_id===viewerId);
    const canViewContents=capsule.status==="revealed"
      ? capsule.audience==="guild"||isOwner||(capsule.audience==="contributors"&&isContributor)
      : capsule.status==="collecting"&&isOwner;
    const message=canViewContents
      ? capsule.description||"No reveal message was added."
      : capsule.status==="failed"
        ? "Delivery requires manual reconciliation. Do not retry until the destination has been checked."
          + (isOwner && capsule.delivery_error ? "\n\nDelivery detail: " + capsule.delivery_error.slice(0,400) : "")
        : capsule.status==="cancelled"
          ? "This capsule was cancelled before its reveal."
          : "The capsule message remains sealed until its scheduled reveal.";
    const embed=new EmbedBuilder().setColor(capsule.status==="revealed"?EMBED_COLOURS.success:EMBED_COLOURS.primary)
      .setTitle("#"+capsule.id+" · "+capsule.title)
      .setDescription(message)
      .addFields(
        {name:"Status",value:capsule.status,inline:true},
        {name:"Audience",value:capsule.audience,inline:true},
        {name:"Scheduled reveal",value:formatDate(capsule.release_at),inline:false},
        {name:"Contributions",value:String(item.contributions.length),inline:true},
      );
    if(capsule.status==="collecting"&&item.contributions.length){
      embed.addFields({name:"Contributors",value:item.contributions.map(x=>"<@"+x.contributor_id+">").join(", ").slice(0,900)});
    }
    const buttons:ButtonBuilder[]=[];
    if(capsule.status==="collecting"){
      buttons.push(new ButtonBuilder().setCustomId("capsule:contribute:"+capsule.id).setLabel("Add / edit contribution").setStyle(ButtonStyle.Primary));
      if(capsule.owner_id===viewerId)buttons.push(new ButtonBuilder().setCustomId("capsule:seal:"+capsule.id).setLabel("Seal capsule").setStyle(ButtonStyle.Success));
    }
    if(capsule.owner_id===viewerId&&["collecting","sealed"].includes(capsule.status)){
      buttons.push(new ButtonBuilder().setCustomId("capsule:cancel:"+capsule.id).setLabel("Cancel").setStyle(ButtonStyle.Danger));
    }
    return {embeds:[embed],components:[
      new ActionRowBuilder<ButtonBuilder>().addComponents(buttons.length?buttons:[new ButtonBuilder().setCustomId("capsule:browse").setLabel("Browse").setStyle(ButtonStyle.Secondary)]),
      new ActionRowBuilder<ButtonBuilder>().addComponents(new ButtonBuilder().setCustomId("capsule:browse").setLabel("Browse").setStyle(ButtonStyle.Secondary)),
    ]};
  }
}
