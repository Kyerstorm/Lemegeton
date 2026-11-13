import {ActionRowBuilder,ButtonBuilder,ButtonStyle,EmbedBuilder,MessageFlags,type ButtonInteraction,type Interaction} from "discord.js";
import {query,queryOne} from "../../database.js";
import { emoji } from "../emoji.js";
import {logger} from "../runtime/logger.js";

export const CONSENT_POLICY_VERSIONS={
 terms:"2026-11-12",
 privacy:"2026-11-12",
 guidelines:"2026-11-12",
} as const;

export const POLICY_LINKS=[
 {label:"Terms of Service",url:"https://github.com/Kyerstorm/Lemegeton/blob/multi_guild/docs/TERMS_OF_SERVICE.md"},
 {label:"Privacy Policy",url:"https://github.com/Kyerstorm/Lemegeton/blob/multi_guild/docs/PRIVACY_POLICY.md"},
 {label:"Community Guidelines",url:"https://github.com/Kyerstorm/Lemegeton/blob/multi_guild/docs/COMMUNITY_GUIDELINES.md"},
] as const;

export function buildConsentEmbed():EmbedBuilder{
 return new EmbedBuilder()
  .setColor(0x62676d)
  .setTitle("Before using Lemegeton")
  .setDescription("Review the policies below before continuing. Acceptance is required once per Discord account for the current policy versions.\n\nThe privacy policy explains what the bot processes, where records may be stored, and which external providers may receive requests. Lemegeton is not end-to-end encrypted.")
  .addFields(POLICY_LINKS.map(policy=>({name:policy.label,value:`[Read the ${policy.label}](${policy.url})`,inline:false})))
  .setFooter({text:`Policy versions: ${CONSENT_POLICY_VERSIONS.terms} · ${CONSENT_POLICY_VERSIONS.privacy} · ${CONSENT_POLICY_VERSIONS.guidelines}`});
}

export function buildConsentComponents(ownerId:string,disabled=false):ActionRowBuilder<ButtonBuilder>[]{
 const links=new ActionRowBuilder<ButtonBuilder>().addComponents(
  ...POLICY_LINKS.map(policy=>new ButtonBuilder().setLabel(policy.label).setStyle(ButtonStyle.Link).setURL(policy.url)),
 );
 const actions=new ActionRowBuilder<ButtonBuilder>().addComponents(
  new ButtonBuilder().setCustomId(`terms-consent:agree:${ownerId}`).setLabel("Agree & Continue").setStyle(ButtonStyle.Primary).setEmoji(emoji.check).setDisabled(disabled),
  new ButtonBuilder().setCustomId(`terms-consent:decline:${ownerId}`).setLabel("Decline").setStyle(ButtonStyle.Secondary).setDisabled(disabled),
 );
 return [links,actions];
}

export function parseConsentAction(customId:string):{action:"agree"|"decline";ownerId:string}|null{
 const match=/^terms-consent:(agree|decline):(\d{17,20})$/.exec(customId);
 return match?{action:match[1] as "agree"|"decline",ownerId:match[2]!}:null;
}

export async function initUserConsentSchema():Promise<void>{
 await query(`CREATE TABLE IF NOT EXISTS bot_user_consents (
  user_id BIGINT PRIMARY KEY,
  terms_version VARCHAR(32) NOT NULL,
  privacy_version VARCHAR(32) NOT NULL,
  guidelines_version VARCHAR(32) NOT NULL,
  accepted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
 )`);
}

export async function userHasCurrentConsent(userId:string):Promise<boolean>{
 const row=await queryOne<{user_id:string}>(`SELECT user_id FROM bot_user_consents
  WHERE user_id=$1 AND terms_version=$2 AND privacy_version=$3 AND guidelines_version=$4`,
  [userId,CONSENT_POLICY_VERSIONS.terms,CONSENT_POLICY_VERSIONS.privacy,CONSENT_POLICY_VERSIONS.guidelines]);
 return row!==null;
}

async function saveCurrentConsent(userId:string):Promise<void>{
 await query(`INSERT INTO bot_user_consents(user_id,terms_version,privacy_version,guidelines_version,accepted_at)
  VALUES($1,$2,$3,$4,NOW())
  ON CONFLICT(user_id) DO UPDATE SET terms_version=EXCLUDED.terms_version,
   privacy_version=EXCLUDED.privacy_version,guidelines_version=EXCLUDED.guidelines_version,accepted_at=NOW()`,
  [userId,CONSENT_POLICY_VERSIONS.terms,CONSENT_POLICY_VERSIONS.privacy,CONSENT_POLICY_VERSIONS.guidelines]);
}

export async function handleConsentButton(interaction:ButtonInteraction):Promise<boolean>{
 const parsed=parseConsentAction(interaction.customId);
 if(!parsed)return false;
 if(parsed.ownerId!==interaction.user.id){
  await interaction.reply({content:"This agreement prompt belongs to another Discord account. Run a command to open your own.",flags:MessageFlags.Ephemeral});
  return true;
 }
 if(parsed.action==="decline"){
  await interaction.update({content:"Agreement declined. Lemegeton commands remain unavailable until you accept the current policies.",embeds:[],components:buildConsentComponents(parsed.ownerId,true)});
  return true;
 }
 try{
  await saveCurrentConsent(interaction.user.id);
  await interaction.update({content:"Agreement saved. You can now use Lemegeton. Please rerun the command you originally tried.",embeds:[],components:buildConsentComponents(parsed.ownerId,true)});
 }catch(error){
  logger.error("Could not save policy agreement",{userId:interaction.user.id,reason:error instanceof Error?error.message:"Unknown database error"});
  await interaction.reply({content:"Your agreement could not be saved. Please try again shortly; commands remain locked until it is recorded.",flags:MessageFlags.Ephemeral});
 }
 return true;
}

export async function requireCurrentConsent(interaction:Interaction):Promise<boolean>{
 if(interaction.user.bot)return true;
 try{
  if(await userHasCurrentConsent(interaction.user.id))return true;
 }catch(error){
  logger.error("Could not verify policy agreement",{userId:interaction.user.id,reason:error instanceof Error?error.message:"Unknown database error"});
  if(interaction.isAutocomplete()){await interaction.respond([]).catch(()=>undefined);return false;}
  if(interaction.isRepliable()&&!interaction.replied&&!interaction.deferred){
   await interaction.reply({content:"Lemegeton cannot verify your policy agreement right now. Please try again shortly.",flags:MessageFlags.Ephemeral}).catch(()=>undefined);
  }
  return false;
 }
 if(interaction.isAutocomplete()){await interaction.respond([]).catch(()=>undefined);return false;}
 if(interaction.isRepliable()&&!interaction.replied&&!interaction.deferred){
  await interaction.reply({embeds:[buildConsentEmbed()],components:buildConsentComponents(interaction.user.id),flags:MessageFlags.Ephemeral});
 }
 return false;
}
