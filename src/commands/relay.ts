import {
  ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder, MessageFlags, ModalBuilder,
  SlashCommandBuilder, StringSelectMenuBuilder, TextInputBuilder, TextInputStyle,
  type ButtonInteraction, type ChatInputCommandInteraction, type ModalSubmitInteraction,
  type StringSelectMenuInteraction,
} from "discord.js";
import type { FeatureCommand } from "../../helpers/commands/command.js";
import { EMBED_COLOURS } from "../../helpers/embeds/core.js";
import {
  createRelayChain, getRelayChain, joinRelayChain, listRelayChains,
  reviewRelayContribution, setRelayChainStatus, submitRelayContribution,
} from "../../helpers/community/relay.js";

function relayModal(customId: string,title: string,fields:Array<{id:string;label:string;paragraph?:boolean;required?:boolean;max?:number}>):ModalBuilder{
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

export class RelayCommand implements FeatureCommand{
  readonly data=new SlashCommandBuilder().setName("relay")
    .setDescription("Create collaborative chains with sequential turns, review and revisions.");

  async execute(interaction:ChatInputCommandInteraction):Promise<void>{
    if(!interaction.guildId){await interaction.reply({content:"Relay chains are available inside a server.",flags:MessageFlags.Ephemeral});return;}
    await interaction.reply({...this.homePayload(),flags:MessageFlags.Ephemeral});
  }

  async handleButton(interaction:ButtonInteraction):Promise<boolean>{
    if(!interaction.customId.startsWith("relay:"))return false;
    const [,action,chainId,contributionId,decision]=interaction.customId.split(":");
    if(!interaction.guildId){await interaction.reply({content:"Relay chains are available inside a server.",flags:MessageFlags.Ephemeral});return true;}
    if(action==="home"){await interaction.update(this.homePayload());return true;}
    if(action==="create"){
      await interaction.showModal(relayModal("relay:create-submit","Create a Relay chain",[
        {id:"title",label:"Chain title",required:true,max:180},
        {id:"premise",label:"Premise and contribution rules",required:true,paragraph:true,max:1_000},
        {id:"limit",label:"Maximum contributions (2–100)",max:3},
        {id:"review",label:"Review mode: owner or automatic",max:20},
      ]));
      return true;
    }
    if(action==="browse"){
      await interaction.deferUpdate();
      await interaction.editReply(await this.browsePayload(interaction.guildId));
      return true;
    }
    if(!chainId)return false;
    const chain=await getRelayChain(interaction.guildId,chainId);
    if(!chain){await interaction.reply({content:"That Relay chain was not found in this server.",flags:MessageFlags.Ephemeral});return true;}
    if(action==="view"){await interaction.update(this.chainPayload(chain,interaction.user.id));return true;}
    if(action==="join"){
      try{
        const joined=await joinRelayChain(interaction.guildId,chainId,interaction.user.id);
        await interaction.reply({content:joined?"You joined the Relay chain.":"You are already a member, or the chain is no longer open.",flags:MessageFlags.Ephemeral});
      }catch(error){await interaction.reply({content:error instanceof Error?error.message:"Could not join this chain.",flags:MessageFlags.Ephemeral});}
      return true;
    }
    if(action==="contribute"){
      if(chain.chain.status!=="open"){await interaction.reply({content:"This chain is not accepting contributions.",flags:MessageFlags.Ephemeral});return true;}
      await interaction.showModal(relayModal("relay:contribute-submit:"+chainId,"Contribute to turn "+chain.chain.current_turn,[
        {id:"content",label:"Your contribution",required:true,paragraph:true,max:1_500},
      ]));
      return true;
    }
    if(action==="pause"||action==="resume"||action==="cancel"){
      try{
        const status=action==="pause"?"paused":action==="resume"?"open":"cancelled";
        await setRelayChainStatus({guildId:interaction.guildId,chainId,actorId:interaction.user.id,status});
        await interaction.update(this.chainPayload((await getRelayChain(interaction.guildId,chainId))!,interaction.user.id));
      }catch(error){await interaction.reply({content:error instanceof Error?error.message:"Could not update the chain.",flags:MessageFlags.Ephemeral});}
      return true;
    }
    if(action==="review"&&contributionId&&(decision==="accept"||decision==="revision")){
      try{
        await reviewRelayContribution({
          guildId:interaction.guildId,chainId,contributionId,reviewerId:interaction.user.id,
          approve:decision==="accept",requestRevision:decision==="revision",
          note:decision==="revision"?"Please revise this contribution before the turn can advance.":undefined,
        });
        await interaction.update(this.chainPayload((await getRelayChain(interaction.guildId,chainId))!,interaction.user.id));
      }catch(error){await interaction.reply({content:error instanceof Error?error.message:"The contribution could not be reviewed.",flags:MessageFlags.Ephemeral});}
      return true;
    }
    return false;
  }

  async handleSelect(interaction:StringSelectMenuInteraction):Promise<boolean>{
    if(!interaction.customId.startsWith("relay:"))return false;
    if(!interaction.guildId){await interaction.reply({content:"Relay chains are available inside a server.",flags:MessageFlags.Ephemeral});return true;}
    if(interaction.customId==="relay:chain-list"){
      const chainId=interaction.values[0];
      const chain=chainId?await getRelayChain(interaction.guildId,chainId):null;
      if(!chain){await interaction.reply({content:"That chain is no longer available.",flags:MessageFlags.Ephemeral});return true;}
      await interaction.update(this.chainPayload(chain,interaction.user.id));
      return true;
    }
    return false;
  }

  async handleModal(interaction:ModalSubmitInteraction):Promise<boolean>{
    if(!interaction.customId.startsWith("relay:"))return false;
    if(!interaction.guildId){await interaction.reply({content:"Relay chains are available inside a server.",flags:MessageFlags.Ephemeral});return true;}
    try{
      if(interaction.customId==="relay:create-submit"){
        const rawLimit=interaction.fields.getTextInputValue("limit").trim();
        const limit=rawLimit?Number(rawLimit):20;
        const rawMode=interaction.fields.getTextInputValue("review").trim().toLowerCase();
        if(rawMode&&rawMode!=="owner"&&rawMode!=="automatic"){
          await interaction.reply({content:"Review mode must be owner or automatic.",flags:MessageFlags.Ephemeral});return true;
        }
        const id=await createRelayChain({
          guildId:interaction.guildId,ownerId:interaction.user.id,
          title:interaction.fields.getTextInputValue("title"),premise:interaction.fields.getTextInputValue("premise"),
          contributionLimit:limit,reviewMode:rawMode==="automatic"?"automatic":"owner",
        });
        await interaction.reply({
          content:"Relay chain **#"+id+"** is open. Contributors can join and submit one sequential turn at a time.",
          components:[new ActionRowBuilder<ButtonBuilder>().addComponents(
            new ButtonBuilder().setCustomId("relay:view:"+id).setLabel("Open chain").setStyle(ButtonStyle.Primary),
          )],
          flags:MessageFlags.Ephemeral,
        });
        return true;
      }
      const [,action,chainId]=interaction.customId.split(":");
      if(action==="contribute-submit"&&chainId){
        const result=await submitRelayContribution({
          guildId:interaction.guildId,chainId,authorId:interaction.user.id,
          content:interaction.fields.getTextInputValue("content"),
        });
        await interaction.reply({
          content:result.status==="accepted"
            ?"Turn "+result.turn+" was accepted automatically."
            :"Turn "+result.turn+" was submitted and is waiting for the chain owner's review.",
          components:[new ActionRowBuilder<ButtonBuilder>().addComponents(
            new ButtonBuilder().setCustomId("relay:view:"+chainId).setLabel("Open chain").setStyle(ButtonStyle.Primary),
          )],
          flags:MessageFlags.Ephemeral,
        });
        return true;
      }
    }catch(error){await interaction.reply({content:error instanceof Error?error.message:"The Relay action could not be completed.",flags:MessageFlags.Ephemeral});return true;}
    return false;
  }

  private homePayload(){
    const embed=new EmbedBuilder().setColor(EMBED_COLOURS.primary).setTitle("Relay")
      .setDescription("Build something one contribution at a time. Each accepted turn advances the chain; the owner can approve it or request a revision.");
    return {embeds:[embed],components:[new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("relay:create").setLabel("Create chain").setStyle(ButtonStyle.Primary),
      new ButtonBuilder().setCustomId("relay:browse").setLabel("Browse chains").setStyle(ButtonStyle.Secondary),
    )]};
  }

  private async browsePayload(guildId:string){
    const chains=await listRelayChains(guildId);
    const embed=new EmbedBuilder().setColor(EMBED_COLOURS.primary).setTitle("Open Relay chains")
      .setDescription(chains.map(item=>"**#"+item.id+" · "+item.title+"**\nTurn "+item.current_turn+" / "+item.contribution_limit+" · "+item.members+" members").join("\n\n").slice(0,3_900)
        ||"There are no open chains in this server.");
    if(!chains.length)return {embeds:[embed],components:[new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("relay:home").setLabel("Back").setStyle(ButtonStyle.Secondary),
    )]};
    const select=new StringSelectMenuBuilder().setCustomId("relay:chain-list").setPlaceholder("Open a chain")
      .addOptions(chains.map(item=>({label:("#"+item.id+" · "+item.title).slice(0,100),value:item.id})));
    return {embeds:[embed],components:[
      new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(select),
      new ActionRowBuilder<ButtonBuilder>().addComponents(new ButtonBuilder().setCustomId("relay:home").setLabel("Back").setStyle(ButtonStyle.Secondary)),
    ]};
  }

  private chainPayload(item:NonNullable<Awaited<ReturnType<typeof getRelayChain>>>,viewerId:string){
    const chain=item.chain;
    const embed=new EmbedBuilder().setColor(chain.status==="completed"?EMBED_COLOURS.success:EMBED_COLOURS.primary)
      .setTitle("#"+chain.id+" · "+chain.title).setDescription(chain.premise.slice(0,2_000))
      .addFields(
        {name:"Status",value:chain.status,inline:true},
        {name:"Turn",value:chain.current_turn+" / "+chain.contribution_limit,inline:true},
        {name:"Review",value:chain.review_mode==="owner"?"Owner approval":"Automatic",inline:true},
      );
    const contributions=item.contributions.filter(row=>row.status==="accepted").slice(-10);
    if(contributions.length)embed.addFields({name:"Accepted chain",value:contributions.map(row=>"**"+row.turn_number+".** "+row.content.slice(0,250)).join("\n\n").slice(0,3_000)});
    if(chain.status==="open")embed.addFields({name:"Next contributor",value:"<@"+item.next_contributor_id+">",inline:true});
    const pending=item.contributions.find(row=>row.status==="pending");
    if(pending)embed.addFields({name:"Waiting for review",value:"Turn "+pending.turn_number+" by <@"+pending.author_id+">\n"+pending.content.slice(0,700)});
    const revisionRequest=item.contributions.find(row=>row.status==="revision_requested"&&(row.author_id===viewerId||chain.owner_id===viewerId));
    if(revisionRequest)embed.addFields({name:"Revision requested",value:"Turn "+revisionRequest.turn_number+" · "+(revisionRequest.review_note??"The owner requested a revision.")+"\n"+revisionRequest.content.slice(0,500)});
    const visibleRevisions=item.revisions.filter(row=>row.author_id===viewerId||chain.owner_id===viewerId).slice(-3);
    if(visibleRevisions.length)embed.addFields({name:"Previous versions",value:visibleRevisions.map(row=>"**Turn "+(item.contributions.find(entry=>entry.id===row.contribution_id)?.turn_number??"?")+" · Version "+row.revision_number+"**\n"+row.content.slice(0,250)+(row.review_note?"\nReview: "+row.review_note.slice(0,120):"")).join("\n\n").slice(0,1_000)});
    if(item.members.length)embed.addFields({name:"Contributors",value:item.members.slice(0,20).map(row=>"<@"+row.user_id+">").join(", ").slice(0,900)});
    const buttons:ButtonBuilder[]=[];
    if(chain.status==="open"){
      buttons.push(
        new ButtonBuilder().setCustomId("relay:join:"+chain.id).setLabel("Join").setStyle(ButtonStyle.Secondary),
        new ButtonBuilder().setCustomId("relay:contribute:"+chain.id).setLabel("Contribute").setStyle(ButtonStyle.Primary),
      );
      if(chain.owner_id===viewerId)buttons.push(new ButtonBuilder().setCustomId("relay:pause:"+chain.id).setLabel("Pause").setStyle(ButtonStyle.Secondary));
    }else if(chain.status==="paused"&&chain.owner_id===viewerId){
      buttons.push(new ButtonBuilder().setCustomId("relay:resume:"+chain.id).setLabel("Resume").setStyle(ButtonStyle.Secondary));
    }
    if(chain.owner_id===viewerId&&(chain.status==="open"||chain.status==="paused")){
      buttons.push(new ButtonBuilder().setCustomId("relay:cancel:"+chain.id).setLabel("Cancel").setStyle(ButtonStyle.Danger));
    }
    const rows=[new ActionRowBuilder<ButtonBuilder>().addComponents(buttons.length?buttons:[new ButtonBuilder().setCustomId("relay:browse").setLabel("Browse").setStyle(ButtonStyle.Secondary)])];
    if(pending&&chain.review_mode==="owner"&&chain.owner_id===viewerId){
      rows.push(new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId("relay:review:"+chain.id+":"+pending.id+":accept").setLabel("Accept turn").setStyle(ButtonStyle.Success),
        new ButtonBuilder().setCustomId("relay:review:"+chain.id+":"+pending.id+":revision").setLabel("Request revision").setStyle(ButtonStyle.Secondary),
      ));
    }
    rows.push(new ActionRowBuilder<ButtonBuilder>().addComponents(new ButtonBuilder().setCustomId("relay:browse").setLabel("Browse").setStyle(ButtonStyle.Secondary)));
    return {embeds:[embed],components:rows};
  }
}
