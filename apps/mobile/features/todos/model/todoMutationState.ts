/** Account-scoped exclusion shared by To-do visits while requests settle. */
export type TodoMutationState = {
  key: string;
  pendingIds: Set<string>;
  togglingIds: Set<string>;
  createId: string | null;
  listeners: Set<() => void>;
};
let current: TodoMutationState | undefined;

export function getTodoMutationState(key: string): TodoMutationState {
  if (current?.key !== key) current = {
    key, pendingIds: new Set(), togglingIds: new Set(), createId: null, listeners: new Set(),
  };
  return current;
}

export function beginTodoMutation(
  state: TodoMutationState, id: string, kind: "row" | "toggle" | "create" = "row",
): (() => void) | null {
  if (state.pendingIds.has(id) || (kind === "create" && state.createId)) return null;
  state.pendingIds.add(id);
  if (kind === "toggle") state.togglingIds.add(id);
  if (kind === "create") state.createId = id;
  state.listeners.forEach((listener) => listener());
  return () => {
    state.pendingIds.delete(id);
    state.togglingIds.delete(id);
    if (state.createId === id) state.createId = null;
    state.listeners.forEach((listener) => listener());
  };
}
