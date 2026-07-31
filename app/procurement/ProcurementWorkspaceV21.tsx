"use client";

import { useState } from "react";
import ProcurementAnalysisCenterPanel from "./ProcurementAnalysisCenterPanel";
import ProcurementWorkspaceV20 from "./ProcurementWorkspaceV20";

export default function ProcurementWorkspaceV21(){
  const [open,setOpen]=useState(false);
  return <><ProcurementWorkspaceV20/><button type="button" onClick={()=>setOpen(true)} style={{position:"fixed",zIndex:860,insetInlineEnd:16,bottom:68,border:0,borderRadius:999,background:"#0f766e",color:"white",padding:"10px 14px",font:"inherit",fontWeight:700,boxShadow:"0 12px 28px rgba(15,23,42,.2)"}}>مرکز تحلیل فراخوان‌ها</button>{open&&<ProcurementAnalysisCenterPanel onClose={()=>setOpen(false)}/>}</>;
}
