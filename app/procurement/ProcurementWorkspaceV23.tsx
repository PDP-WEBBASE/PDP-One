"use client";

import dynamic from "next/dynamic";
import ProcurementStartupSessionResilience from "./ProcurementStartupSessionResilience";
import ProcurementPaginationStableEnhancement from "./ProcurementPaginationStableEnhancement";
import ProcurementManagementPerformanceEnhancement from "./ProcurementManagementPerformanceEnhancement";
import ProcurementNavigationReadCache from "./ProcurementNavigationReadCache";
import ProcurementAnalysisContextInlineEnhancement from "./ProcurementAnalysisContextInlineEnhancement";
import ProcurementFullTitleEnhancement from "./ProcurementFullTitleEnhancement";
import ProcurementSubmissionResultsEnhancements from "./ProcurementSubmissionResultsEnhancements";
import ProcurementWorkspaceEnhancements from "./ProcurementWorkspaceEnhancements";
import ProcurementWorkspaceV22 from "./ProcurementWorkspaceV22";

const ProcurementCompactWorkspaceStableEnhancement = dynamic(
  () => import("./ProcurementCompactWorkspaceStableEnhancement"),
  { ssr: false },
);

export default function ProcurementWorkspaceV23() {
  return <>
    <ProcurementStartupSessionResilience />
    <ProcurementPaginationStableEnhancement />
    <ProcurementManagementPerformanceEnhancement />
    <ProcurementNavigationReadCache />
    <ProcurementAnalysisContextInlineEnhancement />
    <ProcurementWorkspaceV22 />
    <ProcurementWorkspaceEnhancements />
    <ProcurementSubmissionResultsEnhancements />
    <ProcurementCompactWorkspaceStableEnhancement />
    <ProcurementFullTitleEnhancement />
  </>;
}
