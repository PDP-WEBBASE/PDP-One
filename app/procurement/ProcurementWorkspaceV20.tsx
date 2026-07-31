"use client";

import { useState } from "react";
import AutomationControlPanel from "./AutomationControlPanel";
import ProcurementWorkspaceV19 from "./ProcurementWorkspaceV19";

export default function ProcurementWorkspaceV20(){
  const [open,setOpen]=useState(false);
  return <><ProcurementWorkspaceV19/><button type="button" onClick={()=>setOpen(true)} style={{position:"fixed",zIndex:850,insetInlineEnd:172,bottom:68,border:0,borderRadius:999,background:"#b45309",color:"white",padding:"10px 14px",font:"inherit",fontWeight:700,boxShadow:"0 12px 28px rgba(15,23,42,.2)"}}>زمان‌بندی استخراج و AI</button>{open&&<AutomationControlPanel onClose={()=>setOpen(false)}/>}</>;
}
