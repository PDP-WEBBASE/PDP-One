"use client";

import { useRouter } from "next/navigation";
import ProcurementAnalysisCenterPanel from "../ProcurementAnalysisCenterPanel";

export default function ProcurementAnalysisCenterPage(){
  const router=useRouter();
  return <ProcurementAnalysisCenterPanel onClose={()=>router.push("/procurement")}/>;
}
