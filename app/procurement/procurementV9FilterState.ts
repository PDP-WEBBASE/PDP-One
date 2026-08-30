export type ProcurementV9FilterState = {
  sources: string[];
  importance: string[];
  urgency: string[];
  deadlineStatuses: string[];
  publishedFrom: string;
  publishedTo: string;
  opportunityTypes: string[];
  activityDomains: string[];
  provinces: string[];
};

const state: ProcurementV9FilterState = {
  sources: [],
  importance: [],
  urgency: [],
  deadlineStatuses: [],
  publishedFrom: "",
  publishedTo: "",
  opportunityTypes: [],
  activityDomains: [],
  provinces: [],
};

function copy(current: ProcurementV9FilterState): ProcurementV9FilterState {
  return {
    ...current,
    sources: [...current.sources],
    importance: [...current.importance],
    urgency: [...current.urgency],
    deadlineStatuses: [...current.deadlineStatuses],
    opportunityTypes: [...current.opportunityTypes],
    activityDomains: [...current.activityDomains],
    provinces: [...current.provinces],
  };
}

export function getProcurementV9FilterState() {
  return copy(state);
}

export function patchProcurementV9FilterState(next: Partial<ProcurementV9FilterState>) {
  if (next.sources) state.sources = [...next.sources];
  if (next.importance) state.importance = [...next.importance];
  if (next.urgency) state.urgency = [...next.urgency];
  if (next.deadlineStatuses) state.deadlineStatuses = [...next.deadlineStatuses];
  if (next.publishedFrom !== undefined) state.publishedFrom = next.publishedFrom;
  if (next.publishedTo !== undefined) state.publishedTo = next.publishedTo;
  if (next.opportunityTypes) state.opportunityTypes = [...next.opportunityTypes];
  if (next.activityDomains) state.activityDomains = [...next.activityDomains];
  if (next.provinces) state.provinces = [...next.provinces];
  return getProcurementV9FilterState();
}
