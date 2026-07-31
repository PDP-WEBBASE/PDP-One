"use client";

import { useState } from "react";
import CaseFollowUpPanel from "./CaseFollowUpPanel";
import ProcurementWorkspaceV17 from "./ProcurementWorkspaceV17";

export default function ProcurementWorkspaceV18(){
  const [open,setOpen]=useState(false);
  return <><ProcurementWorkspaceV17/><button type="button" onClick={()=>setOpen(true)} style={{position:"fixed",zIndex:830,insetInlineEnd:20,bottom:16,border:0,borderRadius:999,background:"#7c3aed",color:"white",padding:"10px 14px",font:"inherit",fontWeight:700,boxShadow:"0 12px 28px rgba(15,23,42,.2)"}}>پیگیری مسئول و موعد</button>{open&&<CaseFollowUpPanel onClose={()=>setOpen(false)}/>}</>;
}
