"use client";

import dynamic from "next/dynamic";
import ProcurementStartupSessionResilience from "./ProcurementStartupSessionResilience";
import ProcurementPaginationStableEnhancement from "./ProcurementPaginationStableEnhancement";
import ProcurementAnalysisContextInlineEnhancement from "./ProcurementAnalysisContextInlineEnhancement";
import ProcurementFullTitleEnhancement from "./ProcurementFullTitleEnhancement";
import ProcurementWorkflowActionsStableEnhancement from "./ProcurementWorkflowActionsStableEnhancement";
import ProcurementManagementToolsStableEnhancement from "./ProcurementManagementToolsStableEnhancement";
import ProcurementListUxRefinement from "./ProcurementListUxRefinement";
import ProcurementCardLayoutBulkRemoveV2 from "./ProcurementCardLayoutBulkRemoveV2";
import ProcurementInitialRenderBoundary from "./ProcurementInitialRenderBoundary";
import ProcurementWorkspaceV22 from "./ProcurementWorkspaceV22";

const ProcurementCompactWorkspaceStableEnhancement = dynamic(
  () => import("./ProcurementCompactWorkspaceStableEnhancement"),
  { ssr: false },
);

const ProcurementWebPreviewV9Enhancement = dynamic(
  () => import("./ProcurementWebPreviewV9Enhancement"),
  { ssr: false },
);

export default function ProcurementWorkspaceV23() {
  return <ProcurementInitialRenderBoundary>
    <ProcurementStartupSessionResilience />
    <ProcurementPaginationStableEnhancement />
    <ProcurementAnalysisContextInlineEnhancement />
    <ProcurementWorkspaceV22 />
    <ProcurementManagementToolsStableEnhancement />
    <ProcurementWorkflowActionsStableEnhancement />
    <ProcurementCompactWorkspaceStableEnhancement />
    <ProcurementFullTitleEnhancement />
    <ProcurementListUxRefinement />
    <ProcurementCardLayoutBulkRemoveV2 />
    <ProcurementWebPreviewV9Enhancement />
  </ProcurementInitialRenderBoundary>;
}
