/**
 * Home overdue / due-soon cards stay until the user dismisses (X) or completes
 * the reminder. Dismiss is persisted across restarts.
 */
import {
  deletePrefFile,
  prefFilePath,
  readPrefFile,
  safePrefUserId,
  writePrefFile,
} from "@/lib/filePrefs";
import type { HomeUrgentTodo } from "@/lib/api";

type HomeNudgeState = {
  dismissed: Set<string>;
};

type Stored = {
  dismissed: string[];
};

function filePath(userId: string): string | null {
  return prefFilePath(`recall.home-nudges.${safePrefUserId(userId)}.json`);
}

function emptyState(): HomeNudgeState {
  return { dismissed: new Set() };
}

function parseState(raw: string): HomeNudgeState {
  const parsed = JSON.parse(raw) as unknown;
  if (!parsed || typeof parsed !== "object") return emptyState();
  const row = parsed as Partial<Stored>;
  const dismissed = Array.isArray(row.dismissed)
    ? row.dismissed.filter((id): id is string => typeof id === "string")
    : [];
  return { dismissed: new Set(dismissed) };
}

export async function loadHomeNudgeState(userId: string): Promise<HomeNudgeState> {
  const raw = await readPrefFile(filePath(userId));
  if (raw == null) return emptyState();
  try {
    return parseState(raw);
  } catch {
    return emptyState();
  }
}

export async function saveHomeNudgeState(
  userId: string,
  state: HomeNudgeState,
): Promise<void> {
  const stored: Stored = {
    dismissed: [...state.dismissed],
  };
  await writePrefFile(filePath(userId), JSON.stringify(stored));
}

export function pruneHomeNudgeState(
  state: HomeNudgeState,
  openTodoIds: Iterable<string>,
): HomeNudgeState {
  const open = new Set(openTodoIds);
  return {
    dismissed: new Set([...state.dismissed].filter((id) => open.has(id))),
  };
}

export async function clearHomeNudgeState(userId: string): Promise<void> {
  await deletePrefFile(filePath(userId));
}

/** Hide only explicitly dismissed reminders. Overdue stays until X or done. */
export function filterHomeNudgeTodos(
  urgent: HomeUrgentTodo[],
  state: HomeNudgeState,
): HomeUrgentTodo[] {
  return urgent.filter((todo) => !state.dismissed.has(todo.id));
}
