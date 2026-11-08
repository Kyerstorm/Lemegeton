type ErrorShape={code?:unknown,status?:unknown,message?:unknown};

function errorShape(error:unknown):ErrorShape{
 return typeof error==="object"&&error!==null?error as ErrorShape:{};
}

/** Map common Discord API failures to safe explanations without exposing internal exception text. */
export function safeInteractionErrorMessage(error:unknown):string{
 const value=errorShape(error);
 const code=typeof value.code==="number"?value.code:Number.NaN;
 const status=typeof value.status==="number"?value.status:Number.NaN;
 if(code===50013||code===50001){
  return "🔒 Discord denied this action because the bot is missing a required permission or access to the channel.";
 }
 if(code===10008||code===10003){
  return "🔎 The Discord message or channel this action needed is no longer available. Reopen the feature and try again.";
 }
 if(code===10062){
  return "⌛ This interaction expired before it could be completed. Reopen the feature and try again.";
 }
 if(code===50035){
  return "⚠️ Some of the submitted information was invalid. Check the fields and try again.";
 }
 if(status===429){
  return "⏳ Discord is rate-limiting this action. Please wait a moment and try again.";
 }
 if(status>=500&&status<600){
  return "⚠️ Discord is temporarily unavailable. Please try again shortly.";
 }
 if(error instanceof TypeError){
  return "⚠️ The request could not be completed. Check the supplied information and try again.";
 }
 return "⚠️ Something went wrong while running this feature. Please report it with /feedback and include the issue reference shown in the response.";
}
