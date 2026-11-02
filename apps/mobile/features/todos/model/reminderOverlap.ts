import type { Todo } from "@/lib/api";

/** Reminders within this window are treated as overlapping. */
export const REMINDER_OVERLAP_MS = 15 * 60 * 1000;

export function findOverlappingReminder(
  todos: Todo[],
  dueDate: Date,
  options?: { excludeId?: string },
): Todo | null {
  const target = dueDate.getTime();
  if (Number.isNaN(target)) return null;

  for (const todo of todos) {
    if (todo.id === options?.excludeId || todo.checked || !todo.due_at) continue;
    const other = new Date(todo.due_at).getTime();
    if (Number.isNaN(other)) continue;
    if (Math.abs(other - target) < REMINDER_OVERLAP_MS) return todo;
  }
  return null;
}

function sameScheduledTime(a: Todo, b: Todo): boolean {
  if (a.checked || b.checked || !a.due_at || !b.due_at) return false;
  const aTime = new Date(a.due_at).getTime();
  const bTime = new Date(b.due_at).getTime();
  if (Number.isNaN(aTime) || Number.isNaN(bTime)) return false;
  return Math.abs(aTime - bTime) < REMINDER_OVERLAP_MS;
}

/** Keep same-time to-dos in one card. A new card starts when the clock moves. */
export function groupBySameTime(todos: Todo[]): Todo[][] {
  const groups: Todo[][] = [];
  for (const todo of todos) {
    const current = groups[groups.length - 1];
    const previous = current?.[current.length - 1];
    if (current && previous && sameScheduledTime(previous, todo)) current.push(todo);
    else groups.push([todo]);
  }
  return groups;
}

export type ClashCluster = {
  names: string[];
  at: string;
};

/**
 * Open to-dos in one day sheet that fall in the same overlap window.
 * Names follow due time. `at` is the earliest due instant in the cluster.
 */
export function clashClusters(todos: Todo[]): ClashCluster[] {
  const open: { todo: Todo; time: number }[] = [];
  for (const todo of todos) {
    if (todo.checked || !todo.due_at) continue;
    const time = new Date(todo.due_at).getTime();
    if (Number.isNaN(time)) continue;
    open.push({ todo, time });
  }
  open.sort((a, b) => a.time - b.time || a.todo.content.localeCompare(b.todo.content));

  const parent = open.map((_, index) => index);
  const find = (index: number): number => {
    let cursor = index;
    while (parent[cursor] !== cursor) cursor = parent[cursor];
    return cursor;
  };
  const unite = (left: number, right: number) => {
    const rootLeft = find(left);
    const rootRight = find(right);
    if (rootLeft !== rootRight) parent[rootRight] = rootLeft;
  };
  for (let i = 0; i < open.length; i++) {
    for (let j = i + 1; j < open.length; j++) {
      if (open[j].time - open[i].time >= REMINDER_OVERLAP_MS) break;
      unite(i, j);
    }
  }

  const groups = new Map<number, { todo: Todo; time: number }[]>();
  for (let i = 0; i < open.length; i++) {
    const root = find(i);
    const list = groups.get(root) ?? [];
    list.push(open[i]);
    groups.set(root, list);
  }

  const clusters: ClashCluster[] = [];
  for (const nodes of groups.values()) {
    if (nodes.length < 2) continue;
    nodes.sort((a, b) => a.time - b.time || a.todo.content.localeCompare(b.todo.content));
    clusters.push({
      names: nodes.map((node) => node.todo.content),
      at: new Date(nodes[0].time).toISOString(),
    });
  }
  clusters.sort((a, b) => a.at.localeCompare(b.at));
  return clusters;
}
