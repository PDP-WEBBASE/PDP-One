"use client";

import dynamic from "next/dynamic";
import ProcurementStartupSessionResilience from "./ProcurementStartupSessionResilience";
import ProcurementPaginationStableEnhancement from "./ProcurementPaginationStableEnhancement";
import ProcurementTabCacheEnhancement from "./ProcurementTabCacheEnhancement";
import ProcurementManagementPerformanceEnhancement from "./ProcurementManagementPerformanceEnhancement";
import ProcurementNavigationReadCache from "./ProcurementNavigationReadCache";
import ProcurementAnalysisContextInlineEnhancement from "./ProcurementAnalysisContextInlineEnhancement";
import ProcurementPaginationIntegrityEnhancement from "./ProcurementPaginationIntegrityEnhancement";
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
    <ProcurementTabCacheEnhancement />
    <ProcurementManagementPerformanceEnhancement />
    <ProcurementNavigationReadCache />
    <ProcurementAnalysisContextInlineEnhancement />
    <ProcurementPaginationIntegrityEnhancement />
    <ProcurementWorkspaceV22 />
    <ProcurementWorkspaceEnhancements />
    <ProcurementSubmissionResultsEnhancements />
    <ProcurementCompactWorkspaceStableEnhancement />
    <ProcurementFullTitleEnhancement />
  </>;
}
