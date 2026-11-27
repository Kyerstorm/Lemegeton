import {
  ActionRowBuilder,ButtonBuilder,ButtonStyle,EmbedBuilder,MessageFlags,ModalBuilder,
  SlashCommandBuilder,StringSelectMenuBuilder,TextInputBuilder,TextInputStyle,
  PermissionFlagsBits,
  type ButtonInteraction,type ChatInputCommandInteraction,type ModalSubmitInteraction,
  type StringSelectMenuInteraction,
} from "discord.js";
import type {FeatureCommand} from "../../helpers/commands/command.js";
import {EMBED_COLOURS} from "../../helpers/embeds/core.js";
import {
  advanceCouncilProposal,closeCouncilVoting,createCouncilProposal,getCouncilProposal,
  listCouncilProposals,reviewCouncilAmendment,submitCouncilAmendment,submitCouncilVote,
} from "../../helpers/community/council.js";

function councilModal(customId:string,title:string,fields:Array<{id:string;label:string;paragraph?:boolean;required?:boolean;max?:number}>):ModalBuilder{
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

function isManager(interaction:ButtonInteraction|ModalSubmitInteraction):boolean{
  return Boolean(interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild)
    ||interaction.memberPermissions?.has(PermissionFlagsBits.ManageMessages)
    ||interaction.memberPermissions?.has(PermissionFlagsBits.Administrator));
}

export class CouncilCommand implements FeatureCommand{
  readonly data=new SlashCommandBuilder().setName("council")
    .setDescription("Create guild proposals, deliberate on amendments and hold accountable votes.");

  async execute(interaction:ChatInputCommandInteraction):Promise<void>{
    if(!interaction.guildId){await interaction.reply({content:"Council proposals are available inside a server.",flags:MessageFlags.Ephemeral});return;}
    await interaction.reply({...this.homePayload(),flags:MessageFlags.Ephemeral});
  }

  async handleButton(interaction:ButtonInteraction):Promise<boolean>{
    if(!interaction.customId.startsWith("council:"))return false;
    const [,action,proposalId,argument]=interaction.customId.split(":");
    if(!interaction.guildId){await interaction.reply({content:"Council proposals are available inside a server.",flags:MessageFlags.Ephemeral});return true;}
    if(action==="home"){await interaction.update(this.homePayload());return true;}
    if(action==="create"){
      await interaction.showModal(councilModal("council:create-submit","Create a proposal",[
        {id:"title",label:"Proposal title",required:true,max:180},
        {id:"description",label:"Context and proposal details",required:true,paragraph:true,max:2_000},
        {id:"options",label:"Ballot options, one per line (2–10)",required:true,paragraph:true,max:700},
        {id:"method",label:"Voting method: single or multiple",max:20},
        {id:"quorum",label:"Minimum votes required (0 = none)",max:5},
      ]));
      return true;
    }
    if(action==="browse"){
      await interaction.deferUpdate();await interaction.editReply(await this.browsePayload(interaction.guildId));return true;
    }
    if(!proposalId)return false;
    const item=await getCouncilProposal(interaction.guildId,proposalId);
    if(!item){await interaction.reply({content:"That proposal was not found in this server.",flags:MessageFlags.Ephemeral});return true;}
    const owner=item.proposal.owner_id===interaction.user.id;
    if(action==="view"){await interaction.update(this.proposalPayload(item,interaction.user.id));return true;}
    if(action==="amend"){
      if(item.proposal.status!=="deliberation"){await interaction.reply({content:"Amendments are accepted only during deliberation.",flags:MessageFlags.Ephemeral});return true;}
      await interaction.showModal(councilModal("council:amend-submit:"+proposalId,"Suggest an amendment",[
        {id:"amendment",label:"Proposed amendment",required:true,paragraph:true,max:1_000},
      ]));return true;
    }
    if(action==="accept-amendment"||action==="reject-amendment"){
      if(!owner||!argument){await interaction.reply({content:"Only the proposal owner can review amendments.",flags:MessageFlags.Ephemeral});return true;}
      try{
        await reviewCouncilAmendment({
          guildId:interaction.guildId,proposalId,amendmentId:argument,reviewerId:interaction.user.id,
          accept:action==="accept-amendment",
        });
        await interaction.update(this.proposalPayload((await getCouncilProposal(interaction.guildId,proposalId))!,interaction.user.id));
      }catch(error){await interaction.reply({content:error instanceof Error?error.message:"The amendment could not be reviewed.",flags:MessageFlags.Ephemeral});}
      return true;
    }
    if(action==="deliberation"||action==="freeze"){
      try{
        await advanceCouncilProposal({
          guildId:interaction.guildId,proposalId,ownerId:interaction.user.id,
          action:action==="deliberation"?"deliberation":"freeze",
        });
        await interaction.update(this.proposalPayload((await getCouncilProposal(interaction.guildId,proposalId))!,interaction.user.id));
      }catch(error){await interaction.reply({content:error instanceof Error?error.message:"The proposal phase could not be changed.",flags:MessageFlags.Ephemeral});}
      return true;
    }
    if(action==="start-voting"){
      if(!owner){await interaction.reply({content:"Only the proposal owner can start voting.",flags:MessageFlags.Ephemeral});return true;}
      await interaction.showModal(councilModal("council:start-submit:"+proposalId,"Start the voting period",[
        {id:"duration",label:"Duration in minutes (1–10080)",required:true,max:5},
      ]));return true;
    }
    if(action==="close-voting"){
      try{
        const result=await closeCouncilVoting({
          guildId:interaction.guildId,proposalId,actorId:interaction.user.id,canModerate:isManager(interaction),
        });
        await interaction.update(this.proposalPayload((await getCouncilProposal(interaction.guildId,proposalId))!,interaction.user.id));
        await interaction.followUp({
          content:"Voting closed: **"+result.status.toUpperCase()+"** · "+result.votes+" vote(s) · quorum "+result.quorum+".",
          flags:MessageFlags.Ephemeral,
        });
      }catch(error){await interaction.reply({content:error instanceof Error?error.message:"Voting could not be closed.",flags:MessageFlags.Ephemeral});}
      return true;
    }
    if(action==="cancel"){
      try{
        await advanceCouncilProposal({guildId:interaction.guildId,proposalId,ownerId:interaction.user.id,action:"cancel"});
        await interaction.update(this.proposalPayload((await getCouncilProposal(interaction.guildId,proposalId))!,interaction.user.id));
      }catch(error){await interaction.reply({content:error instanceof Error?error.message:"The proposal could not be cancelled.",flags:MessageFlags.Ephemeral});}
      return true;
    }
    return false;
  }

  async handleSelect(interaction:StringSelectMenuInteraction):Promise<boolean>{
    if(!interaction.customId.startsWith("council:"))return false;
    if(!interaction.guildId){await interaction.reply({content:"Council proposals are available inside a server.",flags:MessageFlags.Ephemeral});return true;}
    if(interaction.customId.startsWith("council:amendment-list:")){
      const proposalId=interaction.customId.slice("council:amendment-list:".length);
      const amendmentId=interaction.values[0];
      const item=await getCouncilProposal(interaction.guildId,proposalId);
      const amendment=item?.amendments.find(entry=>entry.id===amendmentId);
      if(!amendment||amendment.status!=="pending"){
        await interaction.reply({content:"That amendment is no longer pending.",flags:MessageFlags.Ephemeral});return true;
      }
      await interaction.reply({
        content:"Review amendment **#"+amendment.id+"** by <@"+amendment.author_id+">:\\n"+amendment.amendment,
        components:[new ActionRowBuilder<ButtonBuilder>().addComponents(
          new ButtonBuilder().setCustomId("council:accept-amendment:"+proposalId+":"+amendmentId).setLabel("Accept amendment").setStyle(ButtonStyle.Success),
          new ButtonBuilder().setCustomId("council:reject-amendment:"+proposalId+":"+amendmentId).setLabel("Reject amendment").setStyle(ButtonStyle.Danger),
        )],
        flags:MessageFlags.Ephemeral,
      });return true;
    }
    if(interaction.customId==="council:proposal-list"){
      const id=interaction.values[0];const item=id?await getCouncilProposal(interaction.guildId,id):null;
      if(!item){await interaction.reply({content:"That proposal is no longer available.",flags:MessageFlags.Ephemeral});return true;}
      await interaction.update(this.proposalPayload(item,interaction.user.id));return true;
    }
    if(interaction.customId.startsWith("council:vote:")){
      if(interaction.user.bot){await interaction.reply({content:"Bot accounts cannot vote.",flags:MessageFlags.Ephemeral});return true;}
      const proposalId=interaction.customId.slice("council:vote:".length);
      try{
        const receipt=await submitCouncilVote({
          guildId:interaction.guildId,proposalId,voterId:interaction.user.id,choices:interaction.values,
        });
        await interaction.reply({
          content:"Your ballot was recorded. Receipt: `"+receipt+"`. Keep it for reference. Voter IDs are stored to prevent duplicate ballots; the ballot is not cryptographically anonymous.",
          flags:MessageFlags.Ephemeral,
        });
      }catch(error){await interaction.reply({content:error instanceof Error?error.message:"Your ballot could not be recorded.",flags:MessageFlags.Ephemeral});}
      return true;
    }
    return false;
  }

  async handleModal(interaction:ModalSubmitInteraction):Promise<boolean>{
    if(!interaction.customId.startsWith("council:"))return false;
    if(!interaction.guildId){await interaction.reply({content:"Council proposals are available inside a server.",flags:MessageFlags.Ephemeral});return true;}
    try{
      const [,action,proposalId]=interaction.customId.split(":");
      if(action==="create-submit"){
        const rawOptions=interaction.fields.getTextInputValue("options").split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
        const methodRaw=interaction.fields.getTextInputValue("method").trim().toLowerCase();
        if(methodRaw&&methodRaw!=="single"&&methodRaw!=="multiple"){
          await interaction.reply({content:"Voting method must be single or multiple.",flags:MessageFlags.Ephemeral});return true;
        }
        const quorumRaw=interaction.fields.getTextInputValue("quorum").trim();
        const quorum=quorumRaw?Number(quorumRaw):0;
        const id=await createCouncilProposal({
          guildId:interaction.guildId,ownerId:interaction.user.id,
          title:interaction.fields.getTextInputValue("title"),
          description:interaction.fields.getTextInputValue("description"),
          options:rawOptions,votingMethod:methodRaw==="multiple"?"multiple":"single",quorum,
        });
        await interaction.reply({
          content:"Proposal **#"+id+"** created in review.",
          components:[new ActionRowBuilder<ButtonBuilder>().addComponents(
            new ButtonBuilder().setCustomId("council:view:"+id).setLabel("Open proposal").setStyle(ButtonStyle.Primary),
          )],
          flags:MessageFlags.Ephemeral,
        });return true;
      }
      if(!proposalId)return false;
      if(action==="amend-submit"){
        const id=await submitCouncilAmendment({
          guildId:interaction.guildId,proposalId,authorId:interaction.user.id,
          amendment:interaction.fields.getTextInputValue("amendment"),
        });
        await interaction.reply({content:"Amendment **#"+id+"** submitted for the proposal owner's review.",flags:MessageFlags.Ephemeral});return true;
      }
      if(action==="start-submit"){
        const duration=Number(interaction.fields.getTextInputValue("duration"));
        await advanceCouncilProposal({
          guildId:interaction.guildId,proposalId,ownerId:interaction.user.id,
          action:"start-voting",durationMinutes:duration,
        });
        await interaction.reply({content:"Voting is now open for "+duration+" minute(s). Each server account may cast one ballot.",flags:MessageFlags.Ephemeral});return true;
      }
    }catch(error){await interaction.reply({content:error instanceof Error?error.message:"The Council action could not be completed.",flags:MessageFlags.Ephemeral});return true;}
    return false;
  }

  private homePayload(){
    const embed=new EmbedBuilder().setColor(EMBED_COLOURS.primary).setTitle("Council")
      .setDescription("Run structured server proposals with a review phase, member amendments, a freeze before voting, an explicit quorum and a published result. Voter identifiers are retained for duplicate prevention; this is not a cryptographically anonymous ballot.");
    return {embeds:[embed],components:[new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("council:create").setLabel("Create proposal").setStyle(ButtonStyle.Primary),
      new ButtonBuilder().setCustomId("council:browse").setLabel("Browse proposals").setStyle(ButtonStyle.Secondary),
    )]};
  }

  private async browsePayload(guildId:string){
    const proposals=await listCouncilProposals(guildId);
    const embed=new EmbedBuilder().setColor(EMBED_COLOURS.primary).setTitle("Server proposals")
      .setDescription(proposals.map(item=>"**#"+item.id+" · "+item.title+"**\n"+item.status+" · "+item.vote_count+" vote(s)").join("\n\n").slice(0,3_900)
        ||"There are no proposals in this server.");
    if(!proposals.length)return {embeds:[embed],components:[new ActionRowBuilder<ButtonBuilder>().addComponents(new ButtonBuilder().setCustomId("council:home").setLabel("Back").setStyle(ButtonStyle.Secondary))]};
    const select=new StringSelectMenuBuilder().setCustomId("council:proposal-list").setPlaceholder("Open a proposal")
      .addOptions(proposals.map(item=>({label:("#"+item.id+" · "+item.title).slice(0,100),value:item.id,description:item.status+" · "+item.vote_count+" votes"})));
    return {embeds:[embed],components:[
      new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(select),
      new ActionRowBuilder<ButtonBuilder>().addComponents(new ButtonBuilder().setCustomId("council:home").setLabel("Back").setStyle(ButtonStyle.Secondary)),
    ]};
  }

  private proposalPayload(item:NonNullable<Awaited<ReturnType<typeof getCouncilProposal>>>,viewerId:string){
    const proposal=item.proposal;
    const owner=proposal.owner_id===viewerId;
    const embed=new EmbedBuilder().setColor(proposal.status==="passed"?EMBED_COLOURS.success:EMBED_COLOURS.primary)
      .setTitle("#"+proposal.id+" · "+proposal.title)
      .setDescription(proposal.description.slice(0,2_500))
      .addFields(
        {name:"Phase",value:proposal.status,inline:true},
        {name:"Method",value:proposal.voting_method,inline:true},
        {name:"Quorum",value:String(proposal.quorum),inline:true},
      );
    if(proposal.status==="voting"&&proposal.ends_at){
      embed.addFields({name:"Voting ends",value:"<t:"+Math.floor(new Date(proposal.ends_at).getTime()/1_000)+":R>",inline:true});
    }
    if(item.amendments.length){
      embed.addFields({name:"Amendments",value:item.amendments.slice(0,8).map(x=>
        "**#"+x.id+" · "+x.status+"** by <@"+x.author_id+">\n"+x.amendment.slice(0,180),
      ).join("\n\n").slice(0,2_000)});
    }
    if(proposal.status==="passed"||proposal.status==="failed"){
      embed.addFields({name:"Final tally",value:item.tally.map(x=>"**"+x.option_label+"** · "+x.votes).join("\n").slice(0,1_000)||"No ballots recorded."});
      embed.setFooter({text:proposal.vote_count+" vote(s) · Final outcome: "+proposal.status});
    }else{
      embed.addFields({name:"Ballot options",value:item.ballots.map((x,i)=>(i+1)+". "+x.option_label).join("\n").slice(0,1_000)});
      embed.setFooter({text:proposal.vote_count+" vote(s) · Individual results stay hidden until voting closes."});
    }
    const rows:Array<ActionRowBuilder<ButtonBuilder>|ActionRowBuilder<StringSelectMenuBuilder>>=[];
    if(owner){
      const controls:ButtonBuilder[]=[];
      if(proposal.status==="review")controls.push(new ButtonBuilder().setCustomId("council:deliberation:"+proposal.id).setLabel("Begin deliberation").setStyle(ButtonStyle.Primary));
      if(proposal.status==="deliberation")controls.push(new ButtonBuilder().setCustomId("council:freeze:"+proposal.id).setLabel("Freeze proposal").setStyle(ButtonStyle.Primary));
      if(proposal.status==="frozen")controls.push(new ButtonBuilder().setCustomId("council:start-voting:"+proposal.id).setLabel("Start voting").setStyle(ButtonStyle.Success));
      if(["review","deliberation","frozen"].includes(proposal.status))controls.push(new ButtonBuilder().setCustomId("council:cancel:"+proposal.id).setLabel("Cancel").setStyle(ButtonStyle.Danger));
      if(controls.length)rows.push(new ActionRowBuilder<ButtonBuilder>().addComponents(controls));
    }
    if(proposal.status==="deliberation"){
      rows.push(new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId("council:amend:"+proposal.id).setLabel("Suggest amendment").setStyle(ButtonStyle.Secondary),
      ));
      const pending=item.amendments.filter(x=>x.status==="pending");
      if(owner&&pending.length){
        const select=new StringSelectMenuBuilder().setCustomId("council:amendment-list:"+proposal.id).setPlaceholder("Choose an amendment to review")
          .addOptions(pending.slice(0,25).map(x=>({label:("#"+x.id+" · "+x.amendment).slice(0,100),value:x.id})));
        rows.push(new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(select));
      }
    }
    if(proposal.status==="voting"){
      if(new Date(proposal.ends_at??"").getTime()>Date.now()){
        const vote=new StringSelectMenuBuilder().setCustomId("council:vote:"+proposal.id).setPlaceholder("Select your ballot option")
          .setMinValues(1).setMaxValues(proposal.max_choices)
          .addOptions(item.ballots.map(x=>({label:x.option_label.slice(0,100),value:x.option_key})));
        rows.push(new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(vote));
      }
      if(owner)rows.push(new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId("council:close-voting:"+proposal.id).setLabel("Close voting").setStyle(ButtonStyle.Secondary),
      ));
    }
    rows.push(new ActionRowBuilder<ButtonBuilder>().addComponents(new ButtonBuilder().setCustomId("council:browse").setLabel("Browse").setStyle(ButtonStyle.Secondary)));
    return {embeds:[embed],components:rows};
  }
}
