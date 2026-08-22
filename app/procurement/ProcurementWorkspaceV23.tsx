"use client";

import dynamic from "next/dynamic";
import ProcurementStartupSessionResilience from "./ProcurementStartupSessionResilience";
import ProcurementPaginationStableEnhancement from "./ProcurementPaginationStableEnhancement";
import ProcurementManagementPerformanceEnhancement from "./ProcurementManagementPerformanceEnhancement";
import ProcurementNavigationReadCache from "./ProcurementNavigationReadCache";
import ProcurementAnalysisContextInlineEnhancement from "./ProcurementAnalysisContextInlineEnhancement";
import ProcurementFullTitleEnhancement from "./ProcurementFullTitleEnhancement";
import ProcurementWorkflowActionsStableEnhancement from "./ProcurementWorkflowActionsStableEnhancement";
import ProcurementManagementToolsStableEnhancement from "./ProcurementManagementToolsStableEnhancement";
import ProcurementListUxRefinement from "./ProcurementListUxRefinement";
import ProcurementCardLayoutBulkRemoveV2 from "./ProcurementCardLayoutBulkRemoveV2";
import ProcurementWebPreviewV9Enhancement from "./ProcurementWebPreviewV9Enhancement";
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
    <ProcurementManagementToolsStableEnhancement />
    <ProcurementWorkflowActionsStableEnhancement />
    <ProcurementCompactWorkspaceStableEnhancement />
    <ProcurementFullTitleEnhancement />
    <ProcurementListUxRefinement />
    <ProcurementCardLayoutBulkRemoveV2 />
    <ProcurementWebPreviewV9Enhancement />
  </>;
}
