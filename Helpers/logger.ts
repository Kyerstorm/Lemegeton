type Level="debug"|"info"|"warn"|"error";type Context=Record<string,unknown>;
const priority:Record<Level,number>={debug:10,info:20,warn:30,error:40};let minimum=20;
export function configureLogger(level:Level):void{minimum=priority[level];}
function write(level:Level,message:string,context?:Context):void{if(priority[level]<minimum)return;const line=JSON.stringify({timestamp:new Date().toISOString(),level,message,...(context&&Object.keys(context).length?{context}:{})});if(level==="error")console.error(line);else if(level==="warn")console.warn(line);else console.log(line);}
export const logger={debug:(m:string,c?:Context)=>write("debug",m,c),info:(m:string,c?:Context)=>write("info",m,c),warn:(m:string,c?:Context)=>write("warn",m,c),error:(m:string,c?:Context)=>write("error",m,c)};
