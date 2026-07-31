"use client";

import { useState } from "react";
import CaseContractDraftPanel from "./CaseContractDraftPanel";
import ProcurementWorkspaceV16 from "./ProcurementWorkspaceV16";

export default function ProcurementWorkspaceV17(){
  const [open,setOpen]=useState(false);
  return <><ProcurementWorkspaceV16/><button type="button" onClick={()=>setOpen(true)} style={{position:"fixed",zIndex:820,insetInlineStart:20,bottom:16,border:0,borderRadius:999,background:"#1d4ed8",color:"white",padding:"10px 14px",font:"inherit",fontWeight:700,boxShadow:"0 12px 28px rgba(15,23,42,.2)"}}>قرارداد از پرونده برنده</button>{open&&<CaseContractDraftPanel onClose={()=>setOpen(false)}/>}</>;
}
