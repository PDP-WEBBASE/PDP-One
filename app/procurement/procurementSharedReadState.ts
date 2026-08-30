type SharedReadState = {
  dashboard: unknown | null;
  sourceNames: string[];
};

type Listener = (state: SharedReadState) => void;

let state: SharedReadState = { dashboard: null, sourceNames: [] };
const listeners = new Set<Listener>();

function publish() {
  const snapshot = { ...state, sourceNames: [...state.sourceNames] };
  for (const listener of listeners) listener(snapshot);
}

export function setProcurementSharedDashboard(value: unknown) {
  state = { ...state, dashboard: value };
  publish();
}

export function setProcurementSharedSourceNames(values: string[]) {
  const normalized = [...new Set(values.map((value) => String(value || "").trim()).filter(Boolean))];
  state = { ...state, sourceNames: normalized };
  publish();
}

export function getProcurementSharedReadState<TDashboard = unknown>() {
  return {
    dashboard: state.dashboard as TDashboard | null,
    sourceNames: [...state.sourceNames],
  };
}

export function subscribeProcurementSharedReadState(listener: Listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
