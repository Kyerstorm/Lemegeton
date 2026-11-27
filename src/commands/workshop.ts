import {
  ActionRowBuilder,ButtonBuilder,ButtonStyle,EmbedBuilder,MessageFlags,ModalBuilder,
  SlashCommandBuilder,StringSelectMenuBuilder,TextInputBuilder,TextInputStyle,
  type ButtonInteraction,type ChatInputCommandInteraction,type ModalSubmitInteraction,
  type StringSelectMenuInteraction,
} from "discord.js";
import type {FeatureCommand} from "../../helpers/commands/command.js";
import {EMBED_COLOURS} from "../../helpers/embeds/core.js";
import {
  createWorkshopProject,createWorkshopSection,getWorkshopProject,listWorkshopProjects,
  reviewWorkshopRevision,setWorkshopProjectStatus,submitWorkshopRevision,
} from "../../helpers/community/workshop.js";

function workshopModal(customId:string,title:string,fields:Array<{id:string;label:string;paragraph?:boolean;required?:boolean;max?:number}>):ModalBuilder{
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

export class WorkshopCommand implements FeatureCommand{
  readonly data=new SlashCommandBuilder().setName("workshop")
    .setDescription("Build collaborative projects through assigned sections and reviewed revisions.");

  async execute(interaction:ChatInputCommandInteraction):Promise<void>{
    if(!interaction.guildId){await interaction.reply({content:"Workshop projects are available inside a server.",flags:MessageFlags.Ephemeral});return;}
    await interaction.reply({...this.homePayload(),flags:MessageFlags.Ephemeral});
  }

  async handleButton(interaction:ButtonInteraction):Promise<boolean>{
    if(!interaction.customId.startsWith("workshop:"))return false;
    const [,action,projectId,sectionId,revisionId]=interaction.customId.split(":");
    if(!interaction.guildId){await interaction.reply({content:"Workshop projects are available inside a server.",flags:MessageFlags.Ephemeral});return true;}
    if(action==="home"){await interaction.update(this.homePayload());return true;}
    if(action==="create"){
      await interaction.showModal(workshopModal("workshop:create-submit","Create a Workshop",[
        {id:"title",label:"Project title",required:true,max:180},
        {id:"description",label:"Project description",required:true,paragraph:true,max:1_000},
      ]));
      return true;
    }
    if(action==="browse"){
      await interaction.deferUpdate();await interaction.editReply(await this.browsePayload(interaction.guildId));return true;
    }
    if(!projectId)return false;
    const item=await getWorkshopProject(interaction.guildId,projectId);
    if(!item){await interaction.reply({content:"That project was not found in this server.",flags:MessageFlags.Ephemeral});return true;}
    if(action==="view"){await interaction.update(this.projectPayload(item,interaction.user.id));return true;}
    if(action==="section"){
      if(item.project.owner_id!==interaction.user.id){await interaction.reply({content:"Only the project owner can add sections.",flags:MessageFlags.Ephemeral});return true;}
      await interaction.showModal(workshopModal("workshop:section-submit:"+projectId,"Add project section",[
        {id:"title",label:"Section title",required:true,max:180},
        {id:"description",label:"Section scope",paragraph:true,max:500},
        {id:"assigned",label:"Assigned Discord user ID (optional)",max:20},
      ]));
      return true;
    }
    if(action==="revision"){
      if(!sectionId){await interaction.reply({content:"Choose a section first.",flags:MessageFlags.Ephemeral});return true;}
      const section=item.sections.find(entry=>entry.id===sectionId);
      if(!section){await interaction.reply({content:"That section was not found.",flags:MessageFlags.Ephemeral});return true;}
      await interaction.showModal(workshopModal("workshop:revision-submit:"+projectId+":"+sectionId,"Submit section revision",[
        {id:"content",label:"Revision content",required:true,paragraph:true,max:4_000},
      ]));
      return true;
    }
    if(action==="approve"||action==="changes"){
      if(!sectionId||!revisionId){await interaction.reply({content:"That revision is not available.",flags:MessageFlags.Ephemeral});return true;}
      try{
        await reviewWorkshopRevision({
          guildId:interaction.guildId,projectId,sectionId,revisionId,reviewerId:interaction.user.id,
          approve:action==="approve",note:action==="changes"?"Please revise this section using the review notes.":undefined,
        });
        await interaction.update(this.projectPayload((await getWorkshopProject(interaction.guildId,projectId))!,interaction.user.id));
      }catch(error){await interaction.reply({content:error instanceof Error?error.message:"The revision could not be reviewed.",flags:MessageFlags.Ephemeral});}
      return true;
    }
    if(["pause","resume","complete","archive","cancel"].includes(action??"")){
      try{
        const status=action==="pause"?"paused":action==="resume"?"open":action==="complete"?"completed":action==="archive"?"archived":"cancelled";
        await setWorkshopProjectStatus({guildId:interaction.guildId,projectId,actorId:interaction.user.id,status});
        await interaction.update(this.projectPayload((await getWorkshopProject(interaction.guildId,projectId))!,interaction.user.id));
      }catch(error){await interaction.reply({content:error instanceof Error?error.message:"The project status could not be updated.",flags:MessageFlags.Ephemeral});}
      return true;
    }
    return false;
  }

  async handleSelect(interaction:StringSelectMenuInteraction):Promise<boolean>{
    if(!interaction.customId.startsWith("workshop:"))return false;
    if(!interaction.guildId){await interaction.reply({content:"Workshop projects are available inside a server.",flags:MessageFlags.Ephemeral});return true;}
    if(interaction.customId==="workshop:project-list"){
      const projectId=interaction.values[0];
      const item=projectId?await getWorkshopProject(interaction.guildId,projectId):null;
      if(!item){await interaction.reply({content:"That project is no longer available.",flags:MessageFlags.Ephemeral});return true;}
      await interaction.update(this.projectPayload(item,interaction.user.id));return true;
    }
    if(interaction.customId.startsWith("workshop:section-list:")){
      const projectId=interaction.customId.slice("workshop:section-list:".length);
      const sectionId=interaction.values[0];
      const item=await getWorkshopProject(interaction.guildId,projectId);
      const section=item?.sections.find(entry=>entry.id===sectionId);
      if(!item||!section){await interaction.reply({content:"That section is no longer available.",flags:MessageFlags.Ephemeral});return true;}
      await interaction.update(this.sectionPayload(item,section.id,interaction.user.id));return true;
    }
    return false;
  }

  async handleModal(interaction:ModalSubmitInteraction):Promise<boolean>{
    if(!interaction.customId.startsWith("workshop:"))return false;
    if(!interaction.guildId){await interaction.reply({content:"Workshop projects are available inside a server.",flags:MessageFlags.Ephemeral});return true;}
    try{
      if(interaction.customId==="workshop:create-submit"){
        const id=await createWorkshopProject({
          guildId:interaction.guildId,ownerId:interaction.user.id,
          title:interaction.fields.getTextInputValue("title"),
          description:interaction.fields.getTextInputValue("description"),
        });
        await interaction.reply({
          content:"Workshop project **#"+id+"** created.",
          components:[new ActionRowBuilder<ButtonBuilder>().addComponents(new ButtonBuilder().setCustomId("workshop:view:"+id).setLabel("Open project").setStyle(ButtonStyle.Primary))],
          flags:MessageFlags.Ephemeral,
        });return true;
      }
      const [,action,projectId,sectionId]=interaction.customId.split(":");
      if(action==="section-submit"&&projectId){
        const id=await createWorkshopSection({
          guildId:interaction.guildId,projectId,ownerId:interaction.user.id,
          title:interaction.fields.getTextInputValue("title"),
          description:interaction.fields.getTextInputValue("description"),
          assignedTo:interaction.fields.getTextInputValue("assigned").trim()||undefined,
        });
        await interaction.reply({content:"Section **#"+id+"** added.",components:[
          new ActionRowBuilder<ButtonBuilder>().addComponents(new ButtonBuilder().setCustomId("workshop:view:"+projectId).setLabel("Open project").setStyle(ButtonStyle.Primary)),
        ],flags:MessageFlags.Ephemeral});return true;
      }
      if(action==="revision-submit"&&projectId&&sectionId){
        const id=await submitWorkshopRevision({
          guildId:interaction.guildId,projectId,sectionId,authorId:interaction.user.id,
          content:interaction.fields.getTextInputValue("content"),
        });
        await interaction.reply({
          content:"Revision **#"+id+"** submitted for owner review.",
          components:[new ActionRowBuilder<ButtonBuilder>().addComponents(new ButtonBuilder().setCustomId("workshop:view:"+projectId).setLabel("Open project").setStyle(ButtonStyle.Primary))],
          flags:MessageFlags.Ephemeral,
        });return true;
      }
    }catch(error){await interaction.reply({content:error instanceof Error?error.message:"The Workshop action could not be completed.",flags:MessageFlags.Ephemeral});return true;}
    return false;
  }

  private homePayload(){
    const embed=new EmbedBuilder().setColor(EMBED_COLOURS.primary).setTitle("Workshop")
      .setDescription("Create a shared project, divide it into sections, assign contributors and retain every submitted revision for review.");
    return {embeds:[embed],components:[new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("workshop:create").setLabel("Create project").setStyle(ButtonStyle.Primary),
      new ButtonBuilder().setCustomId("workshop:browse").setLabel("Browse projects").setStyle(ButtonStyle.Secondary),
    )]};
  }

  private async browsePayload(guildId:string){
    const projects=await listWorkshopProjects(guildId);
    const embed=new EmbedBuilder().setColor(EMBED_COLOURS.primary).setTitle("Open Workshop projects")
      .setDescription(projects.map(item=>"**#"+item.id+" · "+item.title+"**\n"+item.status+" · "+item.section_count+" section(s)").join("\n\n").slice(0,3_900)
        ||"There are no open Workshop projects in this server.");
    if(!projects.length)return {embeds:[embed],components:[new ActionRowBuilder<ButtonBuilder>().addComponents(new ButtonBuilder().setCustomId("workshop:home").setLabel("Back").setStyle(ButtonStyle.Secondary))]};
    const select=new StringSelectMenuBuilder().setCustomId("workshop:project-list").setPlaceholder("Open a project")
      .addOptions(projects.map(item=>({label:("#"+item.id+" · "+item.title).slice(0,100),value:item.id})));
    return {embeds:[embed],components:[
      new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(select),
      new ActionRowBuilder<ButtonBuilder>().addComponents(new ButtonBuilder().setCustomId("workshop:home").setLabel("Back").setStyle(ButtonStyle.Secondary)),
    ]};
  }

  private projectPayload(item:NonNullable<Awaited<ReturnType<typeof getWorkshopProject>>>,viewerId:string){
    const project=item.project;
    const embed=new EmbedBuilder().setColor(project.status==="completed"?EMBED_COLOURS.success:EMBED_COLOURS.primary)
      .setTitle("#"+project.id+" · "+project.title).setDescription(project.description.slice(0,2_000))
      .addFields({name:"Status",value:project.status,inline:true},{name:"Sections",value:String(item.sections.length),inline:true});
    const rows:Array<ActionRowBuilder<ButtonBuilder>|ActionRowBuilder<StringSelectMenuBuilder>>=[];
    if(item.sections.length){
      embed.addFields({name:"Project sections",value:item.sections.map(section=>
        "**#"+section.id+" · "+section.title+"** · "+section.status
          +(section.assigned_to?" · <@"+section.assigned_to+">":""),
      ).join("\n").slice(0,2_000)});
      const select=new StringSelectMenuBuilder().setCustomId("workshop:section-list:"+project.id).setPlaceholder("Open a section")
        .addOptions(item.sections.slice(0,25).map(section=>({label:("#"+section.id+" · "+section.title).slice(0,100),value:section.id})));
      rows.push(new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(select));
    }
    const buttons:ButtonBuilder[]=[];
    if(project.owner_id===viewerId&&project.status==="open"){
      buttons.push(
        new ButtonBuilder().setCustomId("workshop:section:"+project.id).setLabel("Add section").setStyle(ButtonStyle.Primary),
        new ButtonBuilder().setCustomId("workshop:pause:"+project.id).setLabel("Pause").setStyle(ButtonStyle.Secondary),
        new ButtonBuilder().setCustomId("workshop:complete:"+project.id).setLabel("Complete").setStyle(ButtonStyle.Success),
      );
    }else if(project.owner_id===viewerId&&project.status==="paused"){
      buttons.push(new ButtonBuilder().setCustomId("workshop:resume:"+project.id).setLabel("Resume").setStyle(ButtonStyle.Secondary));
    }
    if(buttons.length)rows.push(new ActionRowBuilder<ButtonBuilder>().addComponents(buttons));
    rows.push(new ActionRowBuilder<ButtonBuilder>().addComponents(new ButtonBuilder().setCustomId("workshop:browse").setLabel("Browse").setStyle(ButtonStyle.Secondary)));
    return {embeds:[embed],components:rows};
  }

  private sectionPayload(item:NonNullable<Awaited<ReturnType<typeof getWorkshopProject>>>,sectionId:string,viewerId:string){
    const section=item.sections.find(entry=>entry.id===sectionId)!;
    const revisions=item.revisions.filter(revision=>revision.section_id===sectionId);
    const embed=new EmbedBuilder().setColor(EMBED_COLOURS.primary).setTitle(section.title).setDescription(section.description||"No section description.")
      .addFields({name:"Status",value:section.status,inline:true},{name:"Assigned to",value:section.assigned_to?"<@"+section.assigned_to+">":"Open to contributors",inline:true});
    if(revisions.length)embed.addFields({name:"Revision history",value:revisions.slice(0,8).map(revision=>
      "**#"+revision.id+" · "+revision.status+"** by <@"+revision.author_id+">\n"+revision.content.slice(0,220)
        +(revision.review_note?"\nReview: "+revision.review_note.slice(0,150):""),
    ).join("\n\n").slice(0,3_500)});
    const buttons:ButtonBuilder[]=[];
    if(item.project.status==="open"&&section.status!=="approved"){
      buttons.push(new ButtonBuilder().setCustomId("workshop:revision:"+item.project.id+":"+sectionId).setLabel("Submit revision").setStyle(ButtonStyle.Primary));
    }
    const pending=revisions.find(revision=>revision.status==="pending");
    if(pending&&item.project.owner_id===viewerId){
      buttons.push(
        new ButtonBuilder().setCustomId("workshop:approve:"+item.project.id+":"+sectionId+":"+pending.id).setLabel("Approve latest").setStyle(ButtonStyle.Success),
        new ButtonBuilder().setCustomId("workshop:changes:"+item.project.id+":"+sectionId+":"+pending.id).setLabel("Request changes").setStyle(ButtonStyle.Secondary),
      );
    }
    return {embeds:[embed],components:[
      new ActionRowBuilder<ButtonBuilder>().addComponents(buttons.length?buttons:[new ButtonBuilder().setCustomId("workshop:view:"+item.project.id).setLabel("Back to project").setStyle(ButtonStyle.Secondary)]),
      new ActionRowBuilder<ButtonBuilder>().addComponents(new ButtonBuilder().setCustomId("workshop:view:"+item.project.id).setLabel("Back to project").setStyle(ButtonStyle.Secondary)),
    ]};
  }
}
