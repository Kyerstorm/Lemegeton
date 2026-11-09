import { ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder, type Message } from "discord.js";
import { SteamClient, type SteamStoreGame } from "../steam.js";

const SOCIAL_HOSTS = new Map<string,string>([
  ["x.com","xeezz.com"],
  ["tiktok.com","tiktokez.com"],
  ["ifunny.co","ifunnyez.co"],
  ["reddit.com","redditez.com"],
  ["snapchat.com","snapchatez.com"],
  ["bilibili.com","bilibiliez.com"],
  ["imgur.com","imgurez.com"],
  ["weibo.com","weiboez.com"],
  ["vm.tiktok.com","tiktokez.com"],
]);

/**
 * Returns the legacy community mirror URL for a supported social host.
 * It uses exact host/suffix matching and never rewrites credentials or other domains.
 */
export function rewriteSocialUrl(value:string):string|null {
  let url:URL;
  try { url=new URL(value); }
  catch { return null; }
  if((url.protocol!=="https:"&&url.protocol!=="http:")||url.username||url.password) return null;
  const hostname=url.hostname.toLowerCase();
  const match=[...SOCIAL_HOSTS.entries()].find(([source])=>
    hostname===source || hostname.endsWith("."+source),
  );
  if(!match)return null;
  url.hostname=match[1];
  return url.toString();
}

export function isSupportedSocialUrl(value:string):boolean {
  return rewriteSocialUrl(value)!==null;
}


export function parseSteamStoreAppId(value:string):number|null {
  let url:URL;
  try { url=new URL(value); }
  catch { return null; }
  if(url.protocol!=="https:"||url.hostname.toLowerCase()!=="store.steampowered.com"||url.username||url.password) return null;
  const match=/^\/app\/(\d+)(?:\/|$)/.exec(url.pathname);
  if(!match)return null;
  const appId=Number(match[1]);
  return Number.isSafeInteger(appId)&&appId>0?appId:null;
}

export function buildSteamStoreEmbed(game:SteamStoreGame):EmbedBuilder {
  const fields=[
    {name:"Price",value:game.isFree?"Free":game.price?.final??"Price unavailable",inline:true},
    {name:"Release",value:game.comingSoon?"Coming soon":game.releaseDate??"Date unavailable",inline:true},
    ...(game.developers.length?[{name:"Developer",value:game.developers.join(", ").slice(0,900),inline:false}]:[]),
    ...(game.publishers.length?[{name:"Publisher",value:game.publishers.join(", ").slice(0,900),inline:false}]:[]),
    ...(game.genres.length?[{name:"Genres",value:game.genres.join(", ").slice(0,900),inline:true}]:[]),
  ];
  const embed=new EmbedBuilder()
    .setColor(0x1b2838)
    .setTitle(game.title.slice(0,256))
    .setURL("https://store.steampowered.com/app/"+game.appId)
    .setDescription(game.shortDescription||"No short description supplied by Steam.")
    .addFields(fields)
    .setFooter({text:"Steam Store · Store metadata"});
  if(game.headerImage)embed.setImage(game.headerImage);
  if(game.price&&game.price.discountPercent>0) {
    embed.addFields({name:"Discount",value:game.price.discountPercent+"% off",inline:true});
  }
  return embed;
}

function messageUrls(content:string):string[] {
  return (content.match(/https?:\/\/[^\s<>]+/gi)??[])
    .map(value=>value.replace(/[),.!?\]}]+$/g,""))
    .slice(0,10);
}

/** Adds a Steam Store preview or safe social mirror link without deleting the original message. */
export async function handleSocialLinkMessage(message:Message,steam:SteamClient):Promise<boolean> {
  if(!message.guildId||message.author.bot)return false;
  for(const url of messageUrls(message.content)) {
    const appId=parseSteamStoreAppId(url);
    if(appId!==null) {
      const game=await steam.getStoreGameDetails(appId);
      if(!game)return false;
      await message.reply({
        embeds:[buildSteamStoreEmbed(game)],
        components:[new ActionRowBuilder<ButtonBuilder>().addComponents(
          new ButtonBuilder().setLabel("Open Steam Store").setStyle(ButtonStyle.Link).setURL("https://store.steampowered.com/app/"+game.appId),
        )],
        allowedMentions:{parse:[]},
      });
      return true;
    }
    const rewritten=rewriteSocialUrl(url);
    if(rewritten) {
      const embed=new EmbedBuilder()
        .setColor(0x5865f2)
        .setTitle("Social link")
        .setDescription("[Open alternative preview]("+rewritten+")")
        .setFooter({text:"Original message preserved"});
      await message.reply({
        embeds:[embed],
        components:[new ActionRowBuilder<ButtonBuilder>().addComponents(
          new ButtonBuilder().setLabel("View link").setStyle(ButtonStyle.Link).setURL(rewritten),
        )],
        allowedMentions:{parse:[]},
      });
      return true;
    }
  }
  return false;
}
