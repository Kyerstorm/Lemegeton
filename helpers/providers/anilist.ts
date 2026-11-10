import { secureRandBelow } from "../security/crypto-random.js";
export type AniListMediaType = "ANIME" | "MANGA";
export interface AniListSearchFilters {genre?:string;yearFrom?:number;yearTo?:number;status?:string;format?:string;season?:string;seasonYear?:number;}
function filterVariables(filters:AniListSearchFilters):Record<string,unknown>{return{...(filters.genre?{genreIn:[filters.genre]}:{}),...(filters.yearFrom?{startDateGreater:filters.yearFrom*10000+101}:{}),...(filters.yearTo?{startDateLesser:filters.yearTo*10000+1231}:{}),...(filters.status?{status:filters.status}:{}),...(filters.format?{format:filters.format}:{}),...(filters.season?{season:filters.season}:{}),...(filters.seasonYear?{seasonYear:filters.seasonYear}:{})};}
export interface AniListMedia {
  id:number; type:AniListMediaType;
  title:{romaji:string|null;english:string|null;native:string|null};
  description:string|null; siteUrl:string; coverImage:string|null; bannerImage:string|null;
  averageScore:number|null; status:string|null; format:string|null;
  startDate:{year:number|null;month:number|null;day:number|null}|null;
  episodes:number|null; chapters:number|null; volumes:number|null;
  genres:string[];
  studios:string[];
  staff:string[];
  staffCredits:Array<{id:number;name:string;role:string;url:string;image:string|null}>;
  characters:Array<{id:number;name:string;role:string;url:string;image:string|null}>;
  tags:Array<{name:string;rank:number|null;isSpoiler:boolean}>;
  popularity:number|null;favourites:number|null;source:string|null;
  stats:{statusDistribution:Array<{status:string;amount:number}>;scoreDistribution:Array<{score:number;amount:number}>};
  recommendations:Array<{id:number;title:string;url:string;image:string|null}>;
  relations:Array<{id:number;title:string;relation:string;url:string;category:"anime"|"manga"}>;
  trailer:{id:string;site:string;url:string}|null;
}
export interface AniListCreator {
 id:number;name:string;url:string;image:string|null;description:string|null;
 occupations:string[];yearsActive:number[];media:Array<{title:string;url:string;role:string;type:AniListMediaType}>;
}
export interface AniListFavoriteMedia {id:number;title:string;url:string;image:string|null}
export interface AniListFavoriteCharacter {id:number;name:string;url:string;image:string|null}
export interface AniListFavoritePerson {id:number;name:string;url:string;image:string|null}
export interface AniListPublicActivity {id:number;kind:"TEXT"|"MESSAGE";createdAt:number;url:string;text:string;userName:string;recipientName:string|null}
export type AniListEntityKind = "CHARACTER" | "STAFF" | "STUDIO";
export interface AniListPublicWork {id:number;type:AniListMediaType;title:string;url:string;image:string|null;role:string|null}
export interface AniListPublicEntity {id:number;kind:AniListEntityKind;name:string;url:string;image:string|null;description:string|null;roles:string[];yearsActive:number[];works:AniListPublicWork[]}
export interface AniListReviewRecord {id:number;url:string;summary:string|null;body:string|null;score:number|null;rating:number|null;ratingAmount:number|null;createdAt:number;userName:string;userUrl:string;mediaTitle:string;mediaUrl:string}
export interface AniListUserInterests {
  anime:{genres:string[];tags:string[]};
  manga:{genres:string[];tags:string[]};
}
export interface AniListUserStatistics {
  count:number;
  meanScore:number;
  episodesWatched:number|null;
  minutesWatched:number|null;
  chaptersRead:number|null;
  volumesRead:number|null;
  genres:Array<{genre:string;count:number}>;
  statuses:Array<{status:string;count:number}>;
  formats:Array<{format:string;count:number}>;
}
export interface AniListUserProfile {
  id:number; name:string; url:string; avatar:string|null; banner:string|null; about:string|null;
  anime:AniListUserStatistics;
  manga:AniListUserStatistics;
  favorites:{anime:AniListFavoriteMedia[];manga:AniListFavoriteMedia[];characters:AniListFavoriteCharacter[];staff?:AniListFavoritePerson[];studios?:AniListFavoritePerson[]};
}
export interface AniListRecentlyFinishedMedia {
  id: number;
  type: AniListMediaType;
  title: string;
  description: string | null;
  url: string;
  cover: string | null;
  status: "FINISHED" | "CANCELLED";
  format: string | null;
  episodes: number | null;
  chapters: number | null;
  averageScore: number | null;
  genres: string[];
  endDate: { year: number; month: number; day: number } | null;
}

export interface AniListAiring {
 mediaId:number;title:string;episode:number;airingAt:number;url:string;image:string|null;
 format:string|null;status:string|null;season:string|null;seasonYear:number|null;
}
export interface AniListAiringFilters {
 title?:string;day?:string;season?:string;year?:number;days?:number;
}
export interface AniListMediaNightCandidate {
  id:number;
  type:AniListMediaType;
  title:string;
  url:string;
  image:string|null;
  overview:string|null;
  genres:string[];
  tags:string[];
  year:number|null;
  duration:number|null;
}
type Obj=Record<string,unknown>;
const isObj=(v:unknown):v is Obj=>typeof v==="object"&&v!==null&&!Array.isArray(v);
const str=(v:unknown)=>typeof v==="string"&&v.trim()?v:null;
const num=(v:unknown)=>typeof v==="number"&&Number.isFinite(v)?v:null;
function titleOf(v:unknown):string {const t=isObj(v)?v:{};return str(t.english)??str(t.romaji)??str(t.native)??"Untitled";}
function imageOf(v:unknown):string|null {const o=isObj(v)?v:{};const value=str(o.large)??str(o.extraLarge)??str(o.medium);if(!value)return null;try{const u=new URL(value);return u.protocol==="https:"&&(u.hostname==="anilist.co"||/^s\d+\.anilist\.co$/i.test(u.hostname))?value:null;}catch{return null;}}
export function buildAniListTrailerUrl(site:string|null|undefined,id:string|null|undefined):string|null {
 if(!site||!id)return null;
 const provider=site.trim().toLowerCase();
 const trailerId=id.trim();
 if(provider==="youtube"&&/^[A-Za-z0-9_-]{6,20}$/.test(trailerId))return "https://youtu.be/"+trailerId;
 if(provider==="dailymotion"&&/^[A-Za-z0-9]{4,20}$/.test(trailerId))return "https://www.dailymotion.com/video/"+trailerId;
 return null;
}
function parseTrailer(value:unknown):{id:string;site:string;url:string}|null {
 if(!isObj(value)||typeof value.id!=="string"||typeof value.site!=="string")return null;
 const url=buildAniListTrailerUrl(value.site,value.id);
 return url?{id:value.id,site:value.site,url}:null;
}
function parseMedia(v:unknown):AniListMedia|null {
 if(!isObj(v)||typeof v.id!=="number"||(v.type!=="ANIME"&&v.type!=="MANGA")||v.isAdult===true)return null;
 const t=isObj(v.title)?v.title:{};const d=isObj(v.startDate)?v.startDate:null;const url=str(v.siteUrl);
 if(!url)return null;try{const u=new URL(url);if(u.protocol!=="https:"||u.hostname!=="anilist.co")return null;}catch{return null;}
 const studios=isObj(v.studios)&&Array.isArray(v.studios.nodes)?v.studios.nodes:[];
 const staffContainer=isObj(v.staff)?v.staff:{};
 const staff=Array.isArray(staffContainer.nodes)?staffContainer.nodes
  :Array.isArray(staffContainer.edges)?staffContainer.edges.flatMap(edge=>isObj(edge)&&isObj(edge.node)?[{...edge.node,role:edge.role}]:[])
  :[];
 const edges=isObj(v.relations)&&Array.isArray(v.relations.edges)?v.relations.edges:[];
 return {id:v.id,type:v.type,title:{romaji:str(t.romaji),english:str(t.english),native:str(t.native)},
 description:str(v.description),siteUrl:url,coverImage:imageOf(v.coverImage),
 bannerImage:str(v.bannerImage),averageScore:num(v.averageScore),status:str(v.status),format:str(v.format),
 startDate:d?{year:num(d.year),month:num(d.month),day:num(d.day)}:null,
 episodes:num(v.episodes),chapters:num(v.chapters),volumes:num(v.volumes),
 genres:Array.isArray(v.genres)?v.genres.filter((x):x is string=>typeof x==="string").slice(0,20):[],
 studios:studios.flatMap(x=>isObj(x)&&typeof x.name==="string"?[x.name]:[]).slice(0,8),
 staff:staff.flatMap(x=>isObj(x)&&isObj(x.name)&&typeof x.name.full==="string"?[x.name.full]:[]).slice(0,8),
 staffCredits:staff.flatMap(x=>{
   if(!isObj(x)||!isObj(x.name)||typeof x.id!=="number")return[];
   const url=str(x.siteUrl);if(!url)return[];
   try{const parsed=new URL(url);if(parsed.protocol!=="https:"||parsed.hostname!=="anilist.co")return[];}catch{return[];}
   const id=num(x.id);if(id===null)return[];
   return[{id,name:str(x.name.full)??"Unknown",role:str(x.role)??"Staff",url,image:imageOf(x.image)}];
  }).slice(0,16),
  characters:(isObj(v.characters)&&Array.isArray(v.characters.edges)?v.characters.edges:[]).flatMap(x=>{
   if(!isObj(x)||!isObj(x.node)||typeof x.node.id!=="number"||x.node.isAdult===true)return[];
   const node=x.node,name=isObj(node.name)?str(node.name.full):null;
   if(!name)return[];
   const id=num(node.id);if(id===null)return[];
   return[{id,name,role:str(x.role)??"SUPPORTING",url:`https://anilist.co/character/${id}`,image:imageOf(node.image)}];
  }).slice(0,24),
  tags:(Array.isArray(v.tags)?v.tags:[]).flatMap(x=>isObj(x)&&typeof x.name==="string"&&!x.isAdult?[{name:x.name,rank:num(x.rank),isSpoiler:x.isMediaSpoiler===true}]:[]).slice(0,40),
  popularity:num(v.popularity),favourites:num(v.favourites),source:str(v.source),
  stats:{
   statusDistribution:(isObj(v.stats)&&Array.isArray(v.stats.statusDistribution)?v.stats.statusDistribution:[]).flatMap(x=>isObj(x)&&typeof x.status==="string"?[{status:x.status,amount:num(x.amount)??0}]:[]),
   scoreDistribution:(isObj(v.stats)&&Array.isArray(v.stats.scoreDistribution)?v.stats.scoreDistribution:[]).flatMap(x=>isObj(x)&&num(x.score)!==null?[{score:num(x.score)!,amount:num(x.amount)??0}]:[]),
  },
  recommendations:(isObj(v.recommendations)&&Array.isArray(v.recommendations.edges)?v.recommendations.edges:[]).flatMap(x=>{
   if(!isObj(x)||!isObj(x.node)||!isObj(x.node.mediaRecommendation))return[];
   const item=x.node.mediaRecommendation,u=str(item.siteUrl);
   if(typeof item.id!=="number"||!u)return[];
   try{const parsed=new URL(u);if(parsed.protocol!=="https:"||parsed.hostname!=="anilist.co")return[];}catch{return[];}
   return[{id:item.id,title:titleOf(item.title),url:u,image:imageOf(item.coverImage)}];
  }).slice(0,10),
  relations:edges.flatMap(x=>{if(!isObj(x)||!isObj(x.node)||x.node.isAdult===true)return[];const n=x.node;const u=str(n.siteUrl);if(!u||typeof n.id!=="number"||(n.type!=="ANIME"&&n.type!=="MANGA"))return[];try{const parsed=new URL(u);if(parsed.protocol!=="https:"||parsed.hostname!=="anilist.co")return[];}catch{return[];}return[{id:n.id,title:titleOf(n.title),relation:str(x.relationType)??"RELATED",url:u,category:n.type==="ANIME"?"anime" as const:"manga" as const}];}).slice(0,10),trailer:parseTrailer(v.trailer)};
}
export function parsePublicWork(value:unknown,role:string|null=null):AniListPublicWork|null {
 if(!isObj(value)||typeof value.id!=="number"||(value.type!=="ANIME"&&value.type!=="MANGA")||value.isAdult===true)return null;
 const url=str(value.siteUrl);if(!url)return null;
 try{const parsed=new URL(url);if(parsed.protocol!=="https:"||parsed.hostname!=="anilist.co")return null;}catch{return null;}
 return{id:value.id,type:value.type,title:titleOf(value.title),url,image:imageOf(value.coverImage),role};
}
function parsePublicEntity(value:unknown,kind:AniListEntityKind):AniListPublicEntity|null {
 if(!isObj(value)||typeof value.id!=="number")return null;
 const name=kind==="STUDIO"?str(value.name):isObj(value.name)?str(value.name.full):null;
 const url=str(value.siteUrl);if(!name||!url)return null;
 try{const parsed=new URL(url);if(parsed.protocol!=="https:"||parsed.hostname!=="anilist.co")return null;}catch{return null;}
 const rawWorks=kind==="STAFF"
  ? (isObj(value.staffMedia)&&Array.isArray(value.staffMedia.edges)?value.staffMedia.edges:[])
  : (isObj(value.media)&&Array.isArray(value.media.nodes)?value.media.nodes:[]);
 const works=rawWorks.flatMap(entry=>{
  const isCredit=kind==="STAFF"&&isObj(entry);
  const nodeValue=isCredit?entry.node:entry;
  const roleValue=isCredit?entry.staffRole:null;
  const node=isObj(nodeValue)?nodeValue:{};
  const work=parsePublicWork(node,str(roleValue));
  return work?[work]:[];
 }).slice(0,12);
 return{
  id:value.id,kind,name,url,image:imageOf(kind==="STUDIO"?value:value.image),
  description:str(value.description),
  roles:Array.isArray(value.primaryOccupations)?value.primaryOccupations.filter((item):item is string=>typeof item==="string").slice(0,8):[],
  yearsActive:Array.isArray(value.yearsActive)?value.yearsActive.filter((item):item is number=>typeof item==="number"&&Number.isInteger(item)).slice(0,8):[],
  works,
 };
}
function parsePublicActivity(value:unknown):AniListPublicActivity|null {
 if(!isObj(value))return null;
 const id=num(value.id),createdAt=num(value.createdAt),url=str(value.siteUrl);
 const user=isObj(value.user)?value.user:{},userName=str(user.name);
 if(!id||!createdAt||!url||!userName)return null;
 try{const parsed=new URL(url);if(parsed.protocol!=="https:"||parsed.hostname!=="anilist.co")return null;}catch{return null;}
 const kind=value.message!==undefined?"MESSAGE":value.text!==undefined?"TEXT":null;
 if(!kind)return null;
 return{id,kind,createdAt,url,text:str(kind==="MESSAGE"?value.message:value.text)??"",userName,recipientName:isObj(value.recipient)?str(value.recipient.name):null};
}
function parseReview(value:unknown):AniListReviewRecord|null {
 if(!isObj(value)||typeof value.id!=="number")return null;
 const url=str(value.siteUrl),user=isObj(value.user)?value.user:{},media=isObj(value.media)?value.media:{};
 const userUrl=str(user.siteUrl),mediaUrl=str(media.siteUrl),userName=str(user.name),mediaTitleValue=titleOf(media.title);
 if(!url||!userUrl||!mediaUrl||!userName||media.isAdult===true)return null;
 for(const candidate of [url,userUrl,mediaUrl]){
  try{const parsed=new URL(candidate);if(parsed.protocol!=="https:"||parsed.hostname!=="anilist.co")return null;}catch{return null;}
 }
 return{
  id:value.id,url,summary:str(value.summary),body:str(value.body),
  score:num(value.score),rating:num(value.rating),ratingAmount:num(value.ratingAmount),
  createdAt:num(value.createdAt)??0,userName,userUrl,mediaTitle:mediaTitleValue,mediaUrl,
 };
}
export function parseCreator(value:unknown):AniListCreator|null {
 if(!isObj(value)||typeof value.id!=="number"||!Number.isSafeInteger(value.id))return null;
 const name=isObj(value.name)?str(value.name.full):null;
 const url=str(value.siteUrl);
 if(!name||!url)return null;
 try{const parsed=new URL(url);if(parsed.protocol!=="https:"||parsed.hostname!=="anilist.co"||!parsed.pathname.startsWith("/staff/"))return null;}catch{return null;}
 const connection=isObj(value.staffMedia)&&Array.isArray(value.staffMedia.edges)?value.staffMedia.edges:[];
 const media=connection.flatMap(edge=>{
  if(!isObj(edge)||!isObj(edge.node))return[];
  const node=edge.node;const mediaUrl=str(node.siteUrl);
  if(typeof node.id!=="number"||node.isAdult===true||(node.type!=="ANIME"&&node.type!=="MANGA")||!mediaUrl)return[];
  try{const parsed=new URL(mediaUrl);if(parsed.protocol!=="https:"||parsed.hostname!=="anilist.co")return[];}catch{return[];}
  return[{title:titleOf(node.title),url:mediaUrl,role:str(edge.staffRole)??"Staff",type:node.type as AniListMediaType}];
 }).slice(0,8);
 return {
  id:value.id,name,url,image:imageOf(value.image),description:str(value.description),
  occupations:Array.isArray(value.primaryOccupations)?value.primaryOccupations.filter((x):x is string=>typeof x==="string").slice(0,8):[],
  yearsActive:Array.isArray(value.yearsActive)?value.yearsActive.filter((x):x is number=>typeof x==="number"&&Number.isSafeInteger(x)).slice(0,2):[],
  media,
 };
}
function stats(v:unknown):AniListUserStatistics {
 const o=isObj(v)?v:{};
 const genres=Array.isArray(o.genres)?o.genres.flatMap(x=>isObj(x)&&typeof x.genre==="string"&&typeof x.count==="number"?[{genre:x.genre,count:x.count}]:[]):[];
 const statuses=Array.isArray(o.statuses)?o.statuses.flatMap(x=>isObj(x)&&typeof x.status==="string"&&typeof x.count==="number"?[{status:x.status,count:x.count}]:[]):[];
 const formats=Array.isArray(o.formats)?o.formats.flatMap(x=>isObj(x)&&typeof x.format==="string"&&typeof x.count==="number"?[{format:x.format,count:x.count}]:[]):[];
 return{
  count:num(o.count)??0,meanScore:num(o.meanScore)??0,
  episodesWatched:num(o.episodesWatched),minutesWatched:num(o.minutesWatched),
  chaptersRead:num(o.chaptersRead),volumesRead:num(o.volumesRead),
  genres:genres.sort((x,y)=>y.count-x.count).slice(0,20),
  statuses:statuses.sort((x,y)=>y.count-x.count),
  formats:formats.sort((x,y)=>y.count-x.count),
 };
}
function favoriteMedia(v:unknown):AniListFavoriteMedia[] {
 const nodes=isObj(v)&&Array.isArray(v.nodes)?v.nodes:[];
 return nodes.flatMap(item=>{
  if(!isObj(item)||typeof item.id!=="number")return[];
  const url=str(item.siteUrl);if(!url)return[];
  try{const parsed=new URL(url);if(parsed.protocol!=="https:"||parsed.hostname!=="anilist.co")return[];}catch{return[];}
  return[{id:item.id,title:titleOf(item.title),url,image:imageOf(item.coverImage)}];
 }).slice(0,5);
}
function favoriteCharacters(v:unknown):AniListFavoriteCharacter[] {
 const nodes=isObj(v)&&Array.isArray(v.nodes)?v.nodes:[];
 return nodes.flatMap(item=>{
  if(!isObj(item)||typeof item.id!=="number")return[];
  const name=isObj(item.name)?str(item.name.full):null,url=str(item.siteUrl);
  if(!name||!url)return[];
  try{const parsed=new URL(url);if(parsed.protocol!=="https:"||parsed.hostname!=="anilist.co")return[];}catch{return[];}
  return[{id:item.id,name,url,image:imageOf(item.image)}];
 }).slice(0,5);
}
function favoritePeople(value:unknown,kind:"staff"|"studio"):AniListFavoritePerson[] {
 const nodes=isObj(value)&&Array.isArray(value.nodes)?value.nodes:[];
 return nodes.flatMap(item=>{
  if(!isObj(item)||typeof item.id!=="number")return[];
  const name=kind==="studio"?str(item.name):isObj(item.name)?str(item.name.full):null;
  const url=str(item.siteUrl);
  if(!name||!url)return[];
  try{const parsed=new URL(url);if(parsed.protocol!=="https:"||parsed.hostname!=="anilist.co")return[];}catch{return[];}
  return[{id:item.id,name,url,image:imageOf(kind==="studio"?item:item.image)}];
 }).slice(0,5);
}
function parseInterestSection(value:unknown):AniListUserInterests["anime"] {
 const lists=isObj(value)&&Array.isArray(value.lists)?value.lists:[];
 const genres=new Set<string>(),tags=new Set<string>();
 for(const list of lists){
  const entries=isObj(list)&&Array.isArray(list.entries)?list.entries:[];
  for(const entry of entries){
   const media=isObj(entry)&&isObj(entry.media)?entry.media:{};
   if(Array.isArray(media.genres))for(const genre of media.genres)if(typeof genre==="string"&&genre.trim())genres.add(genre);
   if(Array.isArray(media.tags))for(const tag of media.tags){
    if(isObj(tag)&&tag.isMediaSpoiler!==true&&typeof tag.name==="string"&&tag.name.trim()
      &&typeof tag.rank==="number"&&tag.rank>=75)tags.add(tag.name);
   }
  }
 }
 return{genres:[...genres],tags:[...tags]};
}
const SEARCH=`query Search($search:String,$type:MediaType!,$format:MediaFormat,$sort:[MediaSort],$page:Int,$perPage:Int,$genreIn:[String],$startDateGreater:FuzzyDateInt,$startDateLesser:FuzzyDateInt,$status:MediaStatus,$season:MediaSeason,$seasonYear:Int){Page(page:$page,perPage:$perPage){media(search:$search,type:$type,format:$format,sort:$sort,genre_in:$genreIn,startDate_greater:$startDateGreater,startDate_lesser:$startDateLesser,status:$status,season:$season,seasonYear:$seasonYear){id type title{romaji english native} description(asHtml:false) siteUrl coverImage{large} bannerImage averageScore status format startDate{year month day} episodes chapters volumes genres studios{nodes{name}} staff(page:1,perPage:8){nodes{name{full}}} relations{edges{relationType node{id type isAdult siteUrl title{romaji english}}}} trailer{id site} isAdult}}}}`;
const STAFF_SEARCH=`query CreatorSearch($search:String,$page:Int,$perPage:Int){Page(page:$page,perPage:$perPage){staff(search:$search,sort:SEARCH_MATCH){id name{full} siteUrl image{large} description(asHtml:false) primaryOccupations yearsActive staffMedia(page:1,perPage:8,sort:POPULARITY_DESC){edges{staffRole node{id type isAdult siteUrl title{romaji english native}}}}}}}}`;
const USER=`query User($name:String){User(name:$name){id name siteUrl avatar{large} bannerImage about(asHtml:false) statistics{anime{count meanScore episodesWatched minutesWatched statuses{status count} formats{format count} genres{genre count}} manga{count meanScore chaptersRead volumesRead statuses{status count} formats{format count} genres{genre count}}} favourites{anime(page:1,perPage:5){nodes{id siteUrl title{romaji english native} coverImage{large}}} manga(page:1,perPage:5){nodes{id siteUrl title{romaji english native} coverImage{large}}} characters(page:1,perPage:5){nodes{id siteUrl name{full} image{large}}} staff(page:1,perPage:5){nodes{id siteUrl name{full} image{large}}} studios(page:1,perPage:5){nodes{id siteUrl name}}}}}`;
const TASTE=`query UserTaste($name:String){anime:MediaListCollection(userName:$name,type:ANIME){lists{entries{media{genres tags{name rank isMediaSpoiler}}}}} manga:MediaListCollection(userName:$name,type:MANGA){lists{entries{media{genres tags{name rank isMediaSpoiler}}}}}}}`;
const USER_ACTIVITIES=`query UserActivities($id:Int){User(id:$id){activities(page:1,perPage:8,sort:ID_DESC){... on TextActivity{id siteUrl createdAt text user{name}} ... on MessageActivity{id siteUrl createdAt message user{name} recipient{name}}}}}`;
const CHARACTER_DETAILS=`query CharacterDetails($id:Int!){Character(id:$id){id name{full} siteUrl image{large} description(asHtml:false) gender age favourites media(page:1,perPage:12,sort:POPULARITY_DESC){nodes{id type isAdult title{romaji english native} siteUrl coverImage{large}}}}}`;
const STAFF_DETAILS=`query StaffDetails($id:Int!){Staff(id:$id){id name{full} siteUrl image{large} description(asHtml:false) primaryOccupations yearsActive staffMedia(page:1,perPage:12,sort:POPULARITY_DESC){edges{staffRole node{id type isAdult title{romaji english native} siteUrl coverImage{large}}}}}}`;
const STUDIO_DETAILS=`query StudioDetails($id:Int!){Studio(id:$id){id name siteUrl isAnimationStudio media(page:1,perPage:12,sort:POPULARITY_DESC){nodes{id type isAdult title{romaji english native} siteUrl coverImage{large}}}}}`;
const REVIEW_DETAILS=`query ReviewDetails($id:Int!){Review(id:$id){id summary body score rating ratingAmount createdAt siteUrl user{name siteUrl} media{id type isAdult title{romaji english native} siteUrl}}}`;
const ACTIVITY_DETAILS=`query ActivityDetails($id:Int!){Activity(id:$id){... on TextActivity{id siteUrl createdAt text user{name siteUrl}} ... on MessageActivity{id siteUrl createdAt message user{name siteUrl} recipient{name}}}}`;
const MEDIA_DETAILS=`query MediaDetails($id:Int!,$type:MediaType!){Media(id:$id,type:$type){id type isAdult title{romaji english native} description(asHtml:false) siteUrl coverImage{large} bannerImage averageScore status format startDate{year month day} endDate{year month day} episodes chapters volumes genres studios(isMain:true){nodes{name}} popularity favourites source staff(page:1,perPage:16,sort:RELEVANCE){edges{role node{id name{full} siteUrl image{large}}}} characters(page:1,perPage:24,sort:ROLE){edges{role node{id name{full} image{large} isAdult}}} tags{name rank isMediaSpoiler isAdult} stats{statusDistribution{status amount} scoreDistribution{score amount}} recommendations(sort:RATING,perPage:10){edges{node{mediaRecommendation{id siteUrl title{romaji english native} coverImage{large} isAdult}}}} relations{edges{relationType node{id type isAdult siteUrl title{romaji english}}}} trailer{id site}}}`;
const AIRING=`query Airing($from:Int,$to:Int){Page(page:1,perPage:50){airingSchedules(airingAt_greater:$from,airingAt_lesser:$to,sort:TIME){airingAt episode media{id title{romaji english native} siteUrl coverImage{large} format status season seasonYear isAdult}}}}`;
const AIRING_TITLE=`query TitleAiring($search:String!){Page(page:1,perPage:5){media(search:$search,type:ANIME,sort:SEARCH_MATCH,isAdult:false){id title{romaji english native} siteUrl coverImage{large} format status season seasonYear isAdult airingSchedule(notYetAired:true,perPage:10,sort:TIME){nodes{airingAt episode}}}}}`;
const AIRING_SEASON=`query SeasonAiring($season:MediaSeason,$year:Int){Page(page:1,perPage:50){media(type:ANIME,season:$season,seasonYear:$year,sort:POPULARITY_DESC,isAdult:false){id title{romaji english native} siteUrl coverImage{large} format status season seasonYear isAdult airingSchedule(notYetAired:true,perPage:10,sort:TIME){nodes{airingAt episode}}}}}`;
const AIRING_DAYS=["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"];
const MEDIA_NIGHT_QUERY=`query MediaNight($type:MediaType!){Page(page:1,perPage:50){media(type:$type,sort:TRENDING_DESC,isAdult:false){id type title{romaji english native} description(asHtml:false) siteUrl coverImage{large} startDate{year} duration genres tags{name isMediaSpoiler} isAdult}}}}`;
function parseAiringRows(rows:unknown[]):AniListAiring[]{
 return rows.flatMap(value=>{
  if(!isObj(value)||!isObj(value.media)||value.media.isAdult===true)return[];
  const media=value.media;
  const mediaId=num(media.id),airingAt=num(value.airingAt),episode=num(value.episode),url=str(media.siteUrl);
  if(mediaId===null||mediaId<1||airingAt===null||episode===null||!url)return[];
  try{const parsed=new URL(url);if(parsed.protocol!=="https:"||parsed.hostname!=="anilist.co")return[];}catch{return[];}
  return[{
   mediaId,title:titleOf(media.title),episode,airingAt,url,image:imageOf(media.coverImage),
   format:str(media.format),status:str(media.status),season:str(media.season),seasonYear:num(media.seasonYear),
  }];
 });
}
export class AniListError extends Error {constructor(message:string,readonly statusCode?:number){super(message);this.name="AniListError";}}
export class AniListClient {
 constructor(private readonly endpoint="https://graphql.anilist.co",private readonly timeoutMs=10000,private readonly fetcher:typeof fetch=globalThis.fetch){}
 async search(query:string,type:AniListMediaType,lightNovelOnly=false,filters:AniListSearchFilters={}):Promise<AniListMedia[]>{return this.searchQuery({search:query.trim(),type,...filterVariables(filters),...(lightNovelOnly?{format:"NOVEL"}:{}),sort:"SEARCH_MATCH"});} async random(type:AniListMediaType,lightNovelOnly=false,filters:AniListSearchFilters={}):Promise<AniListMedia[]>{return this.searchQuery({type,...filterVariables(filters),...(lightNovelOnly?{format:"NOVEL"}:{}),sort:"POPULARITY_DESC",page:secureRandBelow(200)+1,perPage:10});}
 async trending(type:AniListMediaType,filters:AniListSearchFilters={}):Promise<AniListMedia[]>{return this.searchQuery({type,...filterVariables(filters),sort:"TRENDING_DESC"});}
 async searchByGenres(type:AniListMediaType,genres:readonly string[],tags:readonly string[]=[],lightNovelOnly=false):Promise<AniListMedia[]>{
  const genreValues=[...new Set(genres.map(value=>value.trim()).filter(Boolean))].slice(0,3);
  const tagValues=[...new Set(tags.map(value=>value.trim()).filter(Boolean))].slice(0,3);
  if(!genreValues.length&&!tagValues.length)return[];
  const query=`query CrossMedia($type:MediaType!,$genres:[String],$tags:[String],$format:MediaFormat){
   Page(page:1,perPage:15){media(type:$type,genre_in:$genres,tag_in:$tags,format:$format,sort:POPULARITY_DESC,isAdult:false){
    id type isAdult title{romaji english native} description(asHtml:false) siteUrl coverImage{large} bannerImage
    averageScore status format startDate{year month day} episodes chapters volumes genres
    tags{name rank isMediaSpoiler isAdult} stats{statusDistribution{status amount} scoreDistribution{score amount}}
    recommendations{edges{node{mediaRecommendation{id siteUrl title{romaji english native} coverImage{large} isAdult}}}}
    relations{edges{relationType node{id type isAdult siteUrl title{romaji english}}}} trailer{id site}
   }}
  }`;
  const data=await this.graphql(query,{type,genres:genreValues,tags:tagValues,format:lightNovelOnly?"NOVEL":null});
  const page=isObj(data.Page)?data.Page:{};
  return(Array.isArray(page.media)?page.media:[]).flatMap(value=>{const media=parseMedia(value);return media?[media]:[];});
 }
 async mediaNightCandidates(type:AniListMediaType):Promise<AniListMediaNightCandidate[]>{
  const data=await this.graphql(MEDIA_NIGHT_QUERY,{type});
  const page=isObj(data.Page)?data.Page:{};
  const rows=Array.isArray(page.media)?page.media:[];
  return rows.flatMap((value):AniListMediaNightCandidate[]=>{
   if(!isObj(value)||value.isAdult===true)return[];
   const parsed=parseMedia(value);if(!parsed)return[];
   const start=isObj(value.startDate)?value.startDate:{};
   const tags=Array.isArray(value.tags)?value.tags.flatMap(tag=>isObj(tag)&&typeof tag.name==="string"&&!tag.isMediaSpoiler?[tag.name]:[]):[];
   return [{
    id:parsed.id,type:parsed.type,title:titleOf(value.title),url:parsed.siteUrl,image:parsed.coverImage,
    overview:parsed.description,genres:parsed.genres,tags,
    year:num(start.year),duration:num(value.duration),
   }];
  });
 }
 async searchCreators(query:string):Promise<AniListCreator[]>{
  const term=query.trim();if(term.length<2)return[];
  const data=await this.graphql(STAFF_SEARCH,{search:term,page:1,perPage:10});
  const page=isObj(data.Page)?data.Page:{};
  return(Array.isArray(page.staff)?page.staff:[]).flatMap(item=>{const creator=parseCreator(item);return creator?[creator]:[];});
 }
 async recommendations(id:number,type:AniListMediaType):Promise<AniListMedia[]>{
  const data=await this.graphql(`query Recs($id:Int,$type:MediaType!){Media(id:$id,type:$type){recommendations(sort:RATING,perPage:10){nodes{mediaRecommendation{id type isAdult title{romaji english native} description(asHtml:false) siteUrl coverImage{large} bannerImage averageScore status format startDate{year month day} episodes chapters volumes genres trailer{id site}}}}}}}`,{id,type});
  const m=isObj(data.Media)?data.Media:{};const rec=isObj(m.recommendations)&&Array.isArray(m.recommendations.nodes)?m.recommendations.nodes:[];
  return rec.flatMap(x=>isObj(x)&&parseMedia(x.mediaRecommendation)?[parseMedia(x.mediaRecommendation)!]:[]);
 }
 async recentlyFinished(type:AniListMediaType, after:Date, before:Date):Promise<AniListRecentlyFinishedMedia[]>{
  const dateKey=(value:Date)=>value.getUTCFullYear()*10000+(value.getUTCMonth()+1)*100+value.getUTCDate();
  const query=`query RecentlyFinished($type:MediaType!,$after:Int!,$before:Int!){
   Page(page:1,perPage:25){
    media(type:$type,status_in:[FINISHED,CANCELLED],sort:END_DATE_DESC,endDate_greater:$after,endDate_lesser:$before){
     id type title{romaji english native} description(asHtml:false) siteUrl coverImage{large}
     status format episodes chapters averageScore genres endDate{year month day}
    }
   }
  }`;
  const data=await this.graphql(query,{type,after:dateKey(after),before:dateKey(before)});
  const page=isObj(data.Page)?data.Page:{};
  const rows=Array.isArray(page.media)?page.media:[];
  return rows.flatMap((value)=>{
   if(!isObj(value))return[];
   const id=num(value.id),url=str(value.siteUrl),status=str(value.status),title=titleOf(value.title);
   const date=isObj(value.endDate)?value.endDate:{};
   const year=num(date.year),month=num(date.month),day=num(date.day);
   if(!id||!url?.startsWith("https://anilist.co/")||!title
     ||(status!=="FINISHED"&&status!=="CANCELLED")||year===null||month===null||day===null
     ||month<1||month>12||day<1||day>31)return[];
   const genres=Array.isArray(value.genres)?value.genres.filter((item):item is string=>typeof item==="string").slice(0,12):[];
   return[{
    id,type,title,description:str(value.description),url,cover:imageOf(value.coverImage),
    status,format:str(value.format),episodes:num(value.episodes),chapters:num(value.chapters),
    averageScore:num(value.averageScore),genres,endDate:{year,month,day},
   } satisfies AniListRecentlyFinishedMedia];
  });
 }
 async getPublicEntity(id:number,kind:AniListEntityKind):Promise<AniListPublicEntity|null>{
  if(!Number.isSafeInteger(id)||id<1)throw new RangeError("AniList entity ID must be a positive integer.");
  const query=kind==="CHARACTER"?CHARACTER_DETAILS:kind==="STAFF"?STAFF_DETAILS:STUDIO_DETAILS;
  const field=kind==="CHARACTER"?"Character":kind==="STAFF"?"Staff":"Studio";
  const data=await this.graphql(query,{id});
  return parsePublicEntity(data[field],kind);
 }
 async getReviewById(id:number):Promise<AniListReviewRecord|null>{
  if(!Number.isSafeInteger(id)||id<1)throw new RangeError("AniList review ID must be a positive integer.");
  const data=await this.graphql(REVIEW_DETAILS,{id});
  return parseReview(data.Review);
 }
 async getActivityById(id:number):Promise<AniListPublicActivity|null>{
  if(!Number.isSafeInteger(id)||id<1)throw new RangeError("AniList activity ID must be a positive integer.");
  const data=await this.graphql(ACTIVITY_DETAILS,{id});
  return parsePublicActivity(data.Activity);
 }
 async getMediaById(id:number,type:AniListMediaType):Promise<AniListMedia|null>{
  if(!Number.isSafeInteger(id)||id<1)throw new RangeError("AniList media ID must be a positive integer.");
  const data=await this.graphql(MEDIA_DETAILS,{id,type});
  return parseMedia(data.Media);
 }
 async getRecentActivities(username:string):Promise<AniListPublicActivity[]>{
  const profile=await this.getUser(username);
  if(!profile)return[];
  const data=await this.graphql(USER_ACTIVITIES,{id:profile.id});
  const user=isObj(data.User)?data.User:{};
  const rows=Array.isArray(user.activities)?user.activities:[];
  return rows.flatMap((value):AniListPublicActivity[]=>{
   if(!isObj(value))return[];
   const activity=parsePublicActivity(value);
   return activity?[activity]:[];
  }).slice(0,8);
 }
 async getUser(username:string):Promise<AniListUserProfile|null>{
  const data=await this.graphql(USER,{name:username.trim()});if(!isObj(data.User))return null;const u=data.User;
  const id=num(u.id),name=str(u.name),url=str(u.siteUrl);if(!id||!name||!url||!url.startsWith("https://anilist.co/"))return null;
  const s=isObj(u.statistics)?u.statistics:{},f=isObj(u.favourites)?u.favourites:{};return{id,name,url,avatar:imageOf(u.avatar),banner:str(u.bannerImage),about:str(u.about),anime:stats(s.anime),manga:stats(s.manga),favorites:{anime:favoriteMedia(f.anime),manga:favoriteMedia(f.manga),characters:favoriteCharacters(f.characters),staff:favoritePeople(f.staff,"staff"),studios:favoritePeople(f.studios,"studio")}};
 }
 async getUserInterests(username:string):Promise<AniListUserInterests|null>{
  const data=await this.graphql(TASTE,{name:username.trim()});
  if(!isObj(data.anime)||!isObj(data.manga))return null;
  return{anime:parseInterestSection(data.anime),manga:parseInterestSection(data.manga)};
 }
 async searchUpcomingAirings(filters:AniListAiringFilters={},now:Date=new Date()):Promise<AniListAiring[]>{
  const days=filters.days??7;
  if(!Number.isInteger(days)||days<1||days>14)throw new Error("Airing window must be between 1 and 14 days.");
  const season=filters.season?.trim().toUpperCase();
  if(season&&!["WINTER","SPRING","SUMMER","FALL"].includes(season))throw new Error("Choose a valid AniList season.");
  if(filters.year!==undefined&&(!Number.isInteger(filters.year)||filters.year<1970||filters.year>2100))throw new Error("Season year must be between 1970 and 2100.");
  const day=filters.day?.trim();
  if(day&&!AIRING_DAYS.some(value=>value.toLowerCase()===day.toLowerCase()))throw new Error("Choose a valid UTC weekday.");
  const title=filters.title?.trim();
  if(title&&title.length>100)throw new Error("Airing title must be 100 characters or fewer.");
  const from=Math.floor(now.getTime()/1000),to=from+days*86400;
  let rows:unknown[]=[];
  if(title){
   const data=await this.graphql(AIRING_TITLE,{search:title});
   const page=isObj(data.Page)?data.Page:{};
   const mediaRows=Array.isArray(page.media)?page.media:[];
   const selected=mediaRows.find(value=>isObj(value)&&value.isAdult!==true&&isObj(value.airingSchedule)
    &&Array.isArray(value.airingSchedule.nodes)&&value.airingSchedule.nodes.length>0);
   if(isObj(selected)&&isObj(selected.airingSchedule)&&Array.isArray(selected.airingSchedule.nodes)){
    rows=selected.airingSchedule.nodes.map(node=>({airingAt:isObj(node)?node.airingAt:null,episode:isObj(node)?node.episode:null,media:selected}));
   }
  }else if(season||filters.year!==undefined){
   const data=await this.graphql(AIRING_SEASON,{season:season??null,year:filters.year??null});
   const page=isObj(data.Page)?data.Page:{};
   const mediaRows=Array.isArray(page.media)?page.media:[];
   rows=mediaRows.flatMap(media=>{
    if(!isObj(media)||media.isAdult===true||!isObj(media.airingSchedule)||!Array.isArray(media.airingSchedule.nodes))return[];
    return media.airingSchedule.nodes.map(node=>({airingAt:isObj(node)?node.airingAt:null,episode:isObj(node)?node.episode:null,media}));
   });
  }else{
   const data=await this.graphql(AIRING,{from,to});
   const page=isObj(data.Page)?data.Page:{};
   rows=Array.isArray(page.airingSchedules)?page.airingSchedules:[];
  }
  return parseAiringRows(rows)
   .filter(entry=>entry.airingAt>from&&entry.airingAt<=to
    &&(!day||AIRING_DAYS[new Date(entry.airingAt*1000).getUTCDay()]?.toLowerCase()===day.toLowerCase())
    &&(!season||entry.season===season)
    &&(filters.year===undefined||entry.seasonYear===filters.year))
   .sort((left,right)=>left.airingAt-right.airingAt);
 }
 async upcomingAirings(from:Date,to:Date):Promise<AniListAiring[]>{
  const data=await this.graphql(AIRING,{from:Math.floor(from.getTime()/1000),to:Math.floor(to.getTime()/1000)});
  const p=isObj(data.Page)?data.Page:{};const rows=Array.isArray(p.airingSchedules)?p.airingSchedules:[];
  return parseAiringRows(rows);
 }
 private async searchQuery(vars:Record<string,unknown>):Promise<AniListMedia[]>{const d=await this.graphql(SEARCH,{page:1,perPage:10,...vars});const p=isObj(d.Page)?d.Page:{};return(Array.isArray(p.media)?p.media:[]).flatMap(x=>{const m=parseMedia(x);return m?[m]:[];});}
 private async graphql(query:string,variables:Record<string,unknown>):Promise<Obj>{
  let response:Response;try{response=await this.fetcher(this.endpoint,{method:"POST",headers:{"Content-Type":"application/json",Accept:"application/json"},body:JSON.stringify({query,variables}),signal:AbortSignal.timeout(this.timeoutMs)});}catch(e){throw new AniListError(e instanceof Error&&["TimeoutError","AbortError"].includes(e.name)?"AniList request timed out.":"AniList could not be reached.");}
  if(!response.ok)throw new AniListError(`AniList returned HTTP ${response.status}.`,response.status);const payload:unknown=await response.json();if(!isObj(payload)||Array.isArray(payload.errors)||!isObj(payload.data))throw new AniListError("AniList returned no usable data.");return payload.data;
 }
}
