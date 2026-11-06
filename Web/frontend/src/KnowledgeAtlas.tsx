import React,{useEffect,useMemo,useRef,useState} from "react";

type AtlasRelation={title:string;category:string;url:string|null;relationType:string;source:string;sourceKind:"provider"|"recommendation"|"community"};
type AtlasRoot={title:string;category:string;url:string|null};
type AtlasResponse={root:AtlasRoot;relationships:AtlasRelation[]};
type Props={guildId:string};
type GraphNode={title:string;category:string;url:string|null;relationType:string;source:string;sourceKind:string};

const VERTEX_SHADER=`#version 300 es
in vec2 a_position;
in vec3 a_color;
in float a_size;
uniform vec2 u_pan;
uniform float u_zoom;
out vec3 v_color;
void main(){vec2 position=a_position*u_zoom+u_pan;gl_Position=vec4(position,0.0,1.0);gl_PointSize=a_size;v_color=a_color;}`;
const FRAGMENT_SHADER=`#version 300 es
precision highp float;
in vec3 v_color;
uniform int u_round;
out vec4 out_color;
void main(){if(u_round==1&&distance(gl_PointCoord,vec2(0.5))>0.5)discard;out_color=vec4(v_color,1.0);}`;

function compileShader(gl:WebGL2RenderingContext,type:number,source:string):WebGLShader{
 const shader=gl.createShader(type);if(!shader)throw new Error("WebGL shader allocation failed.");
 gl.shaderSource(shader,source);gl.compileShader(shader);
 if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS)){const reason=gl.getShaderInfoLog(shader)||"Shader compilation failed.";gl.deleteShader(shader);throw new Error(reason);}
 return shader;
}
function color(source:string):[number,number,number]{
 if(source==="community")return[0.68,0.58,1];
 if(source==="recommendation")return[0.93,0.75,0.48];
 return[0.48,0.65,1];
}
function positions(count:number,aspect:number):Array<{x:number;y:number}>{
 const radiusX=0.78/Math.max(aspect,1),radiusY=0.78*Math.min(aspect,1);
 return[{x:0,y:0},...Array.from({length:count},(_,index)=>{
  const angle=(Math.PI*2*index/Math.max(1,count))-Math.PI/2;
  return{x:Math.cos(angle)*radiusX,y:Math.sin(angle)*radiusY};
 })];
}

function GraphCanvas({nodes,selected,onSelect}:{nodes:GraphNode[];selected:number;onSelect:(index:number)=>void}){
 const canvasRef=useRef<HTMLCanvasElement|null>(null);
 const drawRef=useRef<(()=>void)|null>(null);
 const stateRef=useRef({nodes,selected,zoom:1,panX:0,panY:0});
 const [zoom,setZoom]=useState(1),[pan,setPan]=useState({x:0,y:0});
 const dragRef=useRef<{x:number;y:number;panX:number;panY:number;moved:boolean}|null>(null);
 const [unavailable,setUnavailable]=useState(false);

 useEffect(()=>{stateRef.current={...stateRef.current,nodes,selected,zoom,panX:pan.x,panY:pan.y};drawRef.current?.();},[nodes,selected,zoom,pan]);
 useEffect(()=>{
  const canvas=canvasRef.current;if(!canvas)return;
  const gl=canvas.getContext("webgl2",{antialias:true,alpha:false});
  if(!gl){setUnavailable(true);return;}
  let program:WebGLProgram|undefined,buffer:WebGLBuffer|undefined;
  try{
   const vertex=compileShader(gl,gl.VERTEX_SHADER,VERTEX_SHADER),fragment=compileShader(gl,gl.FRAGMENT_SHADER,FRAGMENT_SHADER);
   program=gl.createProgram()??undefined;if(!program)throw new Error("WebGL program allocation failed.");
   gl.attachShader(program,vertex);gl.attachShader(program,fragment);gl.linkProgram(program);
   gl.deleteShader(vertex);gl.deleteShader(fragment);
   if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(program)||"WebGL program linking failed.");
   buffer=gl.createBuffer()??undefined;if(!buffer)throw new Error("WebGL buffer allocation failed.");
  }catch{setUnavailable(true);return;}
  const position=gl.getAttribLocation(program,"a_position"),tint=gl.getAttribLocation(program,"a_color"),size=gl.getAttribLocation(program,"a_size");
  const panLocation=gl.getUniformLocation(program,"u_pan"),zoomLocation=gl.getUniformLocation(program,"u_zoom"),roundLocation=gl.getUniformLocation(program,"u_round");
  const draw=()=>{
   const current=stateRef.current,rect=canvas.getBoundingClientRect();if(rect.width<1||rect.height<1)return;
   const pixelRatio=Math.min(window.devicePixelRatio||1,2),width=Math.round(rect.width*pixelRatio),height=Math.round(rect.height*pixelRatio);
   if(canvas.width!==width||canvas.height!==height){canvas.width=width;canvas.height=height;}
   gl.viewport(0,0,width,height);gl.clearColor(0.025,0.028,0.034,1);gl.clear(gl.COLOR_BUFFER_BIT);
   gl.useProgram(program!);gl.bindBuffer(gl.ARRAY_BUFFER,buffer!);
   gl.enableVertexAttribArray(position);gl.vertexAttribPointer(position,2,gl.FLOAT,false,24,0);
   gl.enableVertexAttribArray(tint);gl.vertexAttribPointer(tint,3,gl.FLOAT,false,24,8);
   gl.enableVertexAttribArray(size);gl.vertexAttribPointer(size,1,gl.FLOAT,false,24,20);
   gl.uniform2f(panLocation,current.panX,current.panY);gl.uniform1f(zoomLocation,current.zoom);
   const points=positions(Math.max(0,current.nodes.length-1),rect.width/rect.height);
   const edgeVertices:number[]=[];
   for(let index=1;index<points.length;index++){
    const a=points[0],b=points[index],shade=[0.22,0.25,0.30];
    edgeVertices.push(a.x,a.y,...shade,1.5,b.x,b.y,...shade,1.5);
   }
   if(edgeVertices.length){gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(edgeVertices),gl.DYNAMIC_DRAW);gl.uniform1i(roundLocation,0);gl.drawArrays(gl.LINES,0,edgeVertices.length/6);}
   const nodeVertices:number[]=[];
   for(let index=0;index<points.length;index++){
    const node=current.nodes[index];if(!node)continue;
    const shade=index===0?[0.96,0.97,1]:color(node.sourceKind);
    nodeVertices.push(points[index].x,points[index].y,...shade,index===0?24:(current.selected===index?20:14));
   }
   gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(nodeVertices),gl.DYNAMIC_DRAW);gl.uniform1i(roundLocation,1);gl.drawArrays(gl.POINTS,0,nodeVertices.length/6);
  };
  drawRef.current=draw;
  const resize=new ResizeObserver(draw);resize.observe(canvas);window.addEventListener("resize",draw);draw();
  return()=>{resize.disconnect();window.removeEventListener("resize",draw);drawRef.current=null;if(buffer)gl.deleteBuffer(buffer);if(program)gl.deleteProgram(program);};
 },[]);

 const onPointerDown=(event:React.PointerEvent<HTMLCanvasElement>)=>{
  const canvas=canvasRef.current;if(!canvas)return;
  canvas.setPointerCapture(event.pointerId);dragRef.current={x:event.clientX,y:event.clientY,panX:pan.x,panY:pan.y,moved:false};
 };
 const onPointerMove=(event:React.PointerEvent<HTMLCanvasElement>)=>{
  const drag=dragRef.current,canvas=canvasRef.current;if(!drag||!canvas)return;
  const rect=canvas.getBoundingClientRect(),dx=event.clientX-drag.x,dy=event.clientY-drag.y;
  if(Math.hypot(dx,dy)>3)drag.moved=true;
  setPan({x:drag.panX+dx*2/rect.width,y:drag.panY-dy*2/rect.height});
 };
 const onPointerUp=(event:React.PointerEvent<HTMLCanvasElement>)=>{
  const drag=dragRef.current,canvas=canvasRef.current;dragRef.current=null;if(!drag||drag.moved||!canvas)return;
  const rect=canvas.getBoundingClientRect(),clickX=((event.clientX-rect.left)/rect.width)*2-1,clickY=1-((event.clientY-rect.top)/rect.height)*2;
  const points=positions(Math.max(0,nodes.length-1),rect.width/rect.height);
  let nearest=-1,distance=22;
  points.forEach((point,index)=>{
   const x=point.x*zoom+pan.x,y=point.y*zoom+pan.y;
   const dx=(x-clickX)*rect.width/2,dy=(y-clickY)*rect.height/2,score=Math.hypot(dx,dy);
   if(score<distance){distance=score;nearest=index;}
  });
  if(nearest>=0)onSelect(nearest);
 };
 const onWheel=(event:React.WheelEvent<HTMLCanvasElement>)=>{
  event.preventDefault();setZoom((value)=>Math.max(0.55,Math.min(2.6,value*(event.deltaY>0?0.92:1.08))));
 };
 if(unavailable)return <div className="atlas-canvas-fallback">WebGL 2 is unavailable in this browser. The relationship list below remains accessible.</div>;
 return <canvas ref={canvasRef} className="atlas-canvas" aria-label="Interactive media relationship graph. Drag to pan, use the wheel to zoom, and select a node." onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={()=>{dragRef.current=null;}} onWheel={onWheel}/>;
}

export default function KnowledgeAtlas({guildId}:Props){
 const [title,setTitle]=useState(""),[category,setCategory]=useState("ANIME");
 const [data,setData]=useState<AtlasResponse|null>(null),[error,setError]=useState(""),[busy,setBusy]=useState(false),[selected,setSelected]=useState(0);
 const nodes=useMemo<GraphNode[]>(()=>data?[{...data.root,relationType:"Root media",source:"Provider lookup",sourceKind:"root"},...data.relationships]:[],[data]);
 const selectedNode=nodes[selected]??nodes[0];
 const search=async(event:React.FormEvent<HTMLFormElement>)=>{
  event.preventDefault();if(!guildId||!title.trim())return;
  setBusy(true);setError("");
  try{
   const params=new URLSearchParams({title:title.trim(),category});
   const response=await fetch("/api/guilds/"+encodeURIComponent(guildId)+"/atlas?"+params.toString(),{credentials:"same-origin",cache:"no-store"});
   const payload=await response.json().catch(()=>({}));
   if(!response.ok)throw new Error(typeof payload.error==="string"?payload.error:"The Knowledge Atlas could not be loaded.");
   setData(payload as AtlasResponse);setSelected(0);
  }catch(cause){setError(cause instanceof Error?cause.message:"The Knowledge Atlas could not be loaded.");setData(null);}
  finally{setBusy(false);}
 };
 return <div className="atlas-layout">
  <form className="atlas-search" onSubmit={(event)=>void search(event)}>
   <label className="atlas-field">Media title<input value={title} onChange={(event)=>setTitle(event.target.value)} maxLength={256} placeholder="Search a title already present in the Atlas" required/></label>
   <label className="atlas-field">Category<select value={category} onChange={(event)=>setCategory(event.target.value)}><option value="ANIME">Anime</option><option value="MANGA">Manga</option><option value="LIGHT_NOVEL">Light novel</option><option value="WEBNOVEL">Webnovel</option><option value="BOOK">Book</option><option value="MOVIE">Movie</option><option value="TV">TV</option><option value="GAME">Game</option></select></label>
   <button className="button primary" type="submit" disabled={busy||!guildId}>{busy?"Mapping…":"Open graph"}</button>
  </form>
  {error?<div className="atlas-error" role="alert">{error}</div>:null}
  {data?<>
   <div className="atlas-selected"><div><strong>{selectedNode?.title??data.root.title}</strong><small>{selectedNode?.relationType??"Root media"} · {selectedNode?.category??data.root.category}</small></div>{selectedNode?.url?<a className="command-guide" href={selectedNode.url} target="_blank" rel="noreferrer">Open provider ↗</a>:null}</div>
   <div className="atlas-stage"><GraphCanvas nodes={nodes} selected={selected} onSelect={setSelected}/></div>
   <div className="atlas-legend"><span><i className="atlas-dot root"/>Root</span><span><i className="atlas-dot provider"/>Provider</span><span><i className="atlas-dot recommendation"/>Recommendation</span><span><i className="atlas-dot community"/>Community verified</span></div>
   <div className="atlas-results">{nodes.map((node,index)=><button type="button" className="atlas-result" key={node.title+"-"+index} aria-pressed={selected===index} onClick={()=>setSelected(index)}><span className="atlas-result-copy"><strong>{node.title}</strong><small>{node.relationType} · {node.source}</small></span><span className="atlas-result-arrow">↗</span></button>)}</div>
   <p className="footnote">The graph includes source-declared and recorded connections only. It does not infer relationships from similar titles. Community edges are restricted to this server.</p>
  </>:<div className="empty-state">Open a media title to explore its recorded provider and server-approved relationships.</div>}
 </div>;
}
