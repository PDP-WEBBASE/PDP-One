"use client";

import ProcurementStartupSessionResilience from "./ProcurementStartupSessionResilience";
import ProcurementPaginationEnhancement from "./ProcurementPaginationEnhancement";
import ProcurementTabCacheEnhancement from "./ProcurementTabCacheEnhancement";
import ProcurementPaginationIntegrityEnhancement from "./ProcurementPaginationIntegrityEnhancement";
import ProcurementSubmissionResultsEnhancements from "./ProcurementSubmissionResultsEnhancements";
import ProcurementWorkspaceEnhancements from "./ProcurementWorkspaceEnhancements";
import ProcurementWorkspaceV22 from "./ProcurementWorkspaceV22";

export default function ProcurementWorkspaceV23() {
  return <>
    <ProcurementStartupSessionResilience />
    <ProcurementPaginationEnhancement />
    <ProcurementTabCacheEnhancement />
    <ProcurementPaginationIntegrityEnhancement />
    <ProcurementWorkspaceV22 />
    <ProcurementWorkspaceEnhancements />
    <ProcurementSubmissionResultsEnhancements />
  </>;
}