type Level="debug"|"info"|"warn"|"error";
type Context=Record<string,unknown>;
type LogEntry={timestamp:string;level:Level;message:string;context?:Context};
const priority:Record<Level,number>={debug:10,info:20,warn:30,error:40};
const recent:LogEntry[]=[];
let minimum=20;
export function configureLogger(level:Level):void{minimum=priority[level];}
function write(level:Level,message:string,context?:Context):void{
 if(priority[level]<minimum)return;
 const entry:LogEntry={timestamp:new Date().toISOString(),level,message,...(context&&Object.keys(context).length?{context}:{})};
 recent.push(entry);
 if(recent.length>500)recent.splice(0,recent.length-500);
 const line=JSON.stringify(entry);
 if(level==="error")console.error(line);else if(level==="warn")console.warn(line);else console.log(line);
}
export function readRecentLogs(limit=100):LogEntry[]{
 const bounded=Math.max(1,Math.min(250,Number.isSafeInteger(limit)?limit:100));
 return recent.slice(-bounded).reverse();
}
export const logger={debug:(m:string,c?:Context)=>write("debug",m,c),info:(m:string,c?:Context)=>write("info",m,c),warn:(m:string,c?:Context)=>write("warn",m,c),error:(m:string,c?:Context)=>write("error",m,c)};
