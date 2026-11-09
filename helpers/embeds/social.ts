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
