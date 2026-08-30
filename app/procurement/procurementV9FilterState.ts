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

const FILTER_UNIVERSES = {
  sources: ["ستاد ایران", "هزاره", "پارس‌نماد"],
  importance: ["low", "medium", "high", "very_high"],
  urgency: ["critical", "high", "medium", "normal", "unknown"],
  deadlineStatuses: ["expired", "expiring", "available", "unknown"],
  opportunityTypes: ["consulting", "epc", "construction", "unclassified"],
  activityDomains: ["building", "urban", "mep", "renewable", "multi", "undetermined"],
  provinces: [
    "آذربایجان شرقی", "آذربایجان غربی", "اردبیل", "اصفهان", "البرز", "ایلام", "بوشهر", "تهران",
    "چهارمحال و بختیاری", "خراسان جنوبی", "خراسان رضوی", "خراسان شمالی", "خوزستان", "زنجان", "سمنان",
    "سیستان و بلوچستان", "فارس", "قزوین", "قم", "کردستان", "کرمان", "کرمانشاه", "کهگیلویه و بویراحمد",
    "گلستان", "گیلان", "لرستان", "مازندران", "مرکزی", "هرمزگان", "همدان", "یزد",
  ],
} as const;

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

function sameSelection(values: string[], universe: readonly string[]) {
  if (values.length !== universe.length) return false;
  const selected = new Set(values);
  return universe.every((value) => selected.has(value));
}

function querySelection(values: string[], universe: readonly string[]) {
  // Product semantics: the visible "همه" state is no API restriction. Never
  // serialize every known option, because that excludes null/unknown/future values.
  return sameSelection(values, universe) ? [] : [...values];
}

function copy(current: ProcurementV9FilterState): ProcurementV9FilterState {
  return {
    ...current,
    sources: querySelection(current.sources, FILTER_UNIVERSES.sources),
    importance: querySelection(current.importance, FILTER_UNIVERSES.importance),
    urgency: querySelection(current.urgency, FILTER_UNIVERSES.urgency),
    deadlineStatuses: querySelection(current.deadlineStatuses, FILTER_UNIVERSES.deadlineStatuses),
    opportunityTypes: querySelection(current.opportunityTypes, FILTER_UNIVERSES.opportunityTypes),
    activityDomains: querySelection(current.activityDomains, FILTER_UNIVERSES.activityDomains),
    provinces: querySelection(current.provinces, FILTER_UNIVERSES.provinces),
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

export function procurementV9FilterUniverse() {
  return {
    sources: [...FILTER_UNIVERSES.sources],
    importance: [...FILTER_UNIVERSES.importance],
    urgency: [...FILTER_UNIVERSES.urgency],
    deadlineStatuses: [...FILTER_UNIVERSES.deadlineStatuses],
    opportunityTypes: [...FILTER_UNIVERSES.opportunityTypes],
    activityDomains: [...FILTER_UNIVERSES.activityDomains],
    provinces: [...FILTER_UNIVERSES.provinces],
  };
}
