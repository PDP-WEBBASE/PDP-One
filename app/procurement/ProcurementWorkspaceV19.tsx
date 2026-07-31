"use client";

import { useState } from "react";
import ManagementDashboardPanel from "./ManagementDashboardPanel";
import ProcurementWorkspaceV18 from "./ProcurementWorkspaceV18";

export default function ProcurementWorkspaceV19(){
  const [open,setOpen]=useState(false);
  return <><ProcurementWorkspaceV18/><button type="button" onClick={()=>setOpen(true)} style={{position:"fixed",zIndex:840,insetInlineEnd:20,bottom:68,border:0,borderRadius:999,background:"#0f172a",color:"white",padding:"10px 14px",font:"inherit",fontWeight:700,boxShadow:"0 12px 28px rgba(15,23,42,.2)"}}>داشبورد مدیریتی</button>{open&&<ManagementDashboardPanel onClose={()=>setOpen(false)}/>}</>;
}
