"use client";
import { useEffect, useState, type ReactNode } from "react";
import type { IconName } from "./IconRegistry";

const glyphs: Record<IconName, ReactNode> = {
 overview:<><rect x="3.5" y="3.5" width="7" height="7" rx="1"/><rect x="13.5" y="3.5" width="7" height="7" rx="1"/><rect x="3.5" y="13.5" width="7" height="7" rx="1"/><rect x="13.5" y="13.5" width="7" height="7" rx="1"/></>,
 commands:<><path d="M8 5 3.5 12 8 19"/><path d="m16 5 4.5 7-4.5 7"/><path d="m14 3-4 18"/></>,
 atlas:<><circle cx="12" cy="12" r="2.5"/><circle cx="5" cy="6" r="1.5"/><circle cx="19" cy="5" r="1.5"/><circle cx="19" cy="19" r="1.5"/><circle cx="5" cy="18" r="1.5"/><path d="m7 7.2 3.2 3M17 6.5l-3.2 4M17 17.5l-3.2-4M7 17l3.2-3"/></>,
 extensions:<><rect x="3.5" y="3.5" width="7" height="7" rx="1"/><rect x="13.5" y="3.5" width="7" height="7" rx="1"/><rect x="3.5" y="13.5" width="7" height="7" rx="1"/><path d="M17 13.5v7M13.5 17h7"/></>,
 audit:<><circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3.5 2"/></>,
 diagnostics:<path d="M3 13h4l2.2-6 4.2 11 2.2-6H21"/>,
 logs:<><path d="M5 6h14M5 12h14M5 18h14"/><circle cx="3" cy="6" r=".4" fill="currentColor" stroke="none"/><circle cx="3" cy="12" r=".4" fill="currentColor" stroke="none"/><circle cx="3" cy="18" r=".4" fill="currentColor" stroke="none"/></>,
 integrations:<><path d="M4 8h7M13 8h7M4 16h7M13 16h7"/><circle cx="12" cy="8" r="2.5"/><circle cx="12" cy="16" r="2.5"/></>,
 database:<><ellipse cx="12" cy="5.5" rx="8" ry="3"/><path d="M4 5.5v13c0 1.7 3.6 3 8 3s8-1.3 8-3v-13M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/></>,
 refresh:<><path d="M20 7v5h-5"/><path d="M19 12a7 7 0 0 0-12-4.8L5 9M4 17v-5h5"/><path d="M5 12a7 7 0 0 0 12 4.8L19 15"/></>,
 menu:<path d="M4 6h16M4 12h16M4 18h16"/>,
 home:<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-6v-7h-4v7H4a1 1 0 0 1-1-1z"/>,
 retry:<><path d="M20 7v5h-5"/><path d="M19 12a7 7 0 1 0 1 4"/></>,
};

export interface IconProps { name: IconName; size?: number; className?: string; }
export function Icon({name,size=18,className}:IconProps) {
 const [motionAllowed,setMotionAllowed]=useState(false);
 useEffect(()=>{
  const preference=window.matchMedia("(prefers-reduced-motion: reduce)");
  const update=()=>setMotionAllowed(!preference.matches);
  update();
  preference.addEventListener("change",update);
  return ()=>preference.removeEventListener("change",update);
 },[]);
 return <svg aria-hidden="true" className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" focusable="false">
  <g>{glyphs[name]}{motionAllowed?<animateTransform attributeName="transform" type="translate" values="0 0; 0 -1; 0 0" dur="180ms" begin="mouseover" repeatCount="1"/>:null}</g>
 </svg>;
}
