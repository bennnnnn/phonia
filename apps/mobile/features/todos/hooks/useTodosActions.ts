import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Linking } from "react-native";
import { useActionFeedbackOptional } from "@/contexts/actionFeedbackCore";
import { api, type RecurrenceRule, type Todo } from "@/lib/api";
import { getSessionGeneration } from "@/lib/auth";
import { notifyDestructive } from "@/lib/haptics";
import { toDueAtIso } from "@/features/todos/model/dueDate";
import { allowReminderAlerts, shouldTellAlertsOff } from "@/features/todos/model/reminderAlerts";
import { markReminderIdsSeen } from "@/features/todos/model/reminderSeen";
import { buildOptimisticTodo, removeTodoById, replaceTodoById } from "@/features/todos/model/optimisticTodo";
import { beginTodoMutation, getTodoMutationState } from "@/features/todos/model/todoMutationState";
import { DEFAULT_TOPIC } from "@/features/todos/model/todoTopics";
import { alertDialog, confirmDialog } from "@/ui/overlay/dialogs";

type Params = {
  token: string | null;
  userId: string | undefined;
  todos: Todo[];
  getTodos?: () => Todo[];
  isCurrentSession?: () => boolean;
  isCurrentView?: () => boolean;
  markSeenIds?: (ids: string[]) => Promise<void>;
  setTodos: React.Dispatch<React.SetStateAction<Todo[]>>;
  refresh: (opts?: { silent?: boolean; force?: boolean; afterPending?: boolean }) => Promise<void>;
};
const alwaysCurrent = () => true;

export function useTodosActions({ token, userId, todos, getTodos,
  isCurrentSession = alwaysCurrent, isCurrentView = alwaysCurrent, markSeenIds,
  setTodos, refresh,
}: Params) {
  const { t } = useTranslation();
  const feedback = useActionFeedbackOptional();
  const session = getSessionGeneration();
  const signedIn = Boolean(token);
  const owner = useMemo(() => ({ session, signedIn, userId,
    mutations: getTodoMutationState(`${session}:${userId ?? ""}`),
  }), [session, signedIn, userId]);
  const ownerRef = useRef(owner);
  ownerRef.current = owner;
  const todosRef = useRef(todos);
  todosRef.current = todos;
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  const isSameOwner = useCallback(() => owner.signedIn && ownerRef.current === owner &&
    getSessionGeneration() === owner.session && isCurrentSession(), [owner, isCurrentSession]);
  const canAct = useCallback(() => mounted.current && isSameOwner() && isCurrentView(),
    [isSameOwner, isCurrentView]);
  const [, redraw] = useState(0);
  useEffect(() => {
    const changed = () => { if (mounted.current && isSameOwner()) redraw((value) => value + 1); };
    owner.mutations.listeners.add(changed);
    return () => { owner.mutations.listeners.delete(changed); };
  }, [owner, isSameOwner]);
  const [editorState, setEditorState] = useState<{ owner: typeof owner; value: Todo | null }>({ owner, value: null });
  const editorRef = useRef(editorState);
  const editingTodo = editorState.owner === owner ? editorState.value : null;
  const setEditingTodo = useCallback((todo: Todo | null) => {
    if (!canAct()) return;
    const next = { owner, value: todo };
    editorRef.current = next;
    setEditorState(next);
  }, [canAct, owner]);
  const reportError = useCallback((bodyKey: string) => {
    if (!canAct()) return;
    if (feedback) feedback.error(t(bodyKey));
    else void alertDialog({ title: t("todos.error"), message: t(bodyKey) });
  }, [canAct, feedback, t]);

  // A to-do with a time asks for alerts before it saves, so its reminder sync may schedule;
  // a user who said no is told once per session, with a way to Settings, without holding the save.
  const askForAlerts = useCallback(async (dueIso: string | null) => {
    if (!dueIso || (await allowReminderAlerts()) === "on" || !shouldTellAlertsOff()) return;
    void confirmDialog({
      title: t("todos.alerts_off_title"),
      message: t("todos.alerts_off"),
      confirmLabel: t("todos.alerts_open_settings"),
    }).then((open) => {
      if (open) void Linking.openSettings();
    });
  }, [t]);
  const latestTodo = useCallback((id: string) => (getTodos?.() ?? todosRef.current).find((item) => item.id === id), [getTodos]);
  const applyTodos = useCallback((update: (rows: Todo[]) => Todo[]) => {
    if (isSameOwner()) setTodos(update);
  }, [isSameOwner, setTodos]);
  // After a failed change only: a change that worked returns its row, which is applied
  // as is. Every change used to read the whole list again (code-health audit NET-16).
  const reconcile = useCallback(() => {
    if (isSameOwner()) void refresh({ silent: true, force: true, afterPending: true });
  }, [isSameOwner, refresh]);

  const mutateRow = useCallback(async (
    id: string, change: (snapshot: Todo) => Todo | null,
    request: (snapshot: Todo) => Promise<Todo | null>, errorKey: string,
    kind: "row" | "toggle" = "row",
  ): Promise<boolean> => {
    if (!canAct()) return false;
    const snapshot = latestTodo(id);
    if (!snapshot) return false;
    const release = beginTodoMutation(owner.mutations, id, kind);
    if (!release) return false;
    const optimistic = change(snapshot);
    applyTodos((rows) => optimistic ? replaceTodoById(rows, id, optimistic) : removeTodoById(rows, id));
    try {
      const updated = await request(snapshot);
      applyTodos((rows) => updated ? replaceTodoById(rows, id, updated) : removeTodoById(rows, id));
      return true;
    } catch {
      applyTodos((rows) => replaceTodoById(rows, id, snapshot));
      reportError(errorKey);
      reconcile();
      return false;
    } finally {
      release();
    }
  }, [canAct, latestTodo, owner, applyTodos, reportError, reconcile]);

  const handleCreateTodo = useCallback(async (
    content: string,
    dueDate: Date | null,
    onCreated: () => void,
    recurrence: RecurrenceRule | null = null,
    topic: string = DEFAULT_TOPIC,
  ) => {
    if (!token || !canAct()) return;
    const trimmed = content.trim();
    if (!trimmed) return;
    if (dueDate && !Number.isFinite(dueDate.getTime())) {
      reportError("todos.error_create");
      return;
    }
    const dueIso = dueDate ? toDueAtIso(dueDate) : null;
    await askForAlerts(dueIso);
    if (!canAct()) return;
    const recurrenceRule = dueIso ? recurrence : null;
    const nextTopic = topic.trim() || DEFAULT_TOPIC;
    const optimistic = buildOptimisticTodo({
      content: trimmed,
      topic: nextTopic,
      dueAt: dueIso,
      recurrenceRule,
    });
    const release = beginTodoMutation(owner.mutations, optimistic.id, "create");
    if (!release) return;
    applyTodos((rows) => [optimistic, ...rows]);
    try {
      const created = await api.createTodo(token, trimmed, nextTopic, {
        dueAt: dueIso,
        recurrenceRule,
      });
      applyTodos((rows) => replaceTodoById(rows, optimistic.id, created));
      if (created.due_at && isSameOwner()) {
        if (markSeenIds) void markSeenIds([created.id]);
        else if (userId) void markReminderIdsSeen(userId, [created.id]);
      }
      if (canAct()) {
        onCreated();
      }
    } catch {
      applyTodos((rows) => removeTodoById(rows, optimistic.id));
      reportError("todos.error_create");
      reconcile();
    } finally {
      release();
    }
  }, [token, canAct, reportError, owner, applyTodos, isSameOwner, markSeenIds, userId, reconcile, askForAlerts]);

  const handleToggle = useCallback(async (todo: Todo) => {
    if (!token) return;
    await mutateRow(todo.id, (snapshot) => ({
      ...snapshot,
      checked: !snapshot.checked,
      updated_at: snapshot.checked ? snapshot.updated_at : new Date().toISOString(),
    }),
      (snapshot) => api.updateTodo(token, todo.id, { checked: !snapshot.checked }), "todos.error_update", "toggle");
  }, [token, mutateRow]);

  const handleDeleteItem = useCallback((todo: Todo) => {
    if (!token || !canAct() || owner.mutations.pendingIds.has(todo.id)) return;
    const current = latestTodo(todo.id);
    if (!current) return;
    void confirmDialog({
      title: t("todos.delete_confirm"),
      message: t("todos.delete_confirm_body", { title: current.content }),
      cancelLabel: t("common.cancel"),
      confirmLabel: t("common.delete"),
      destructive: true,
    }).then(async (ok) => {
      if (!ok) return;
      const deleted = await mutateRow(todo.id, () => null, async () => {
        await api.deleteTodo(token, todo.id);
        return null;
      }, "todos.error_delete");
      if (deleted) notifyDestructive();
    });
  }, [token, canAct, owner, latestTodo, t, mutateRow]);

  const openTodoEditor = useCallback((todo: Todo) => {
    if (!canAct() || owner.mutations.pendingIds.has(todo.id)) return;
    const current = latestTodo(todo.id);
    if (!current) return;
    setEditingTodo(current);
  }, [canAct, owner, latestTodo, setEditingTodo]);

  const closeTodoEditor = useCallback(() => {
    setEditingTodo(null);
  }, [setEditingTodo]);

  // Saves content + due + repeat from the edit sheet. The todo argument must
  // still be the open target — a retained callback from a replaced target
  // must not save (see useTodosActionsSafety tests).
  const handleUpdateTodo = useCallback(async (
    todo: Todo,
    content: string,
    date: Date | null,
    recurrence: RecurrenceRule | null,
    topic: string = todo.topic,
    closeOnSave = true,
  ): Promise<boolean> => {
    if (!token || !canAct()) return false;
    if (editorRef.current.owner !== owner || editorRef.current.value?.id !== todo.id) return false;
    const trimmed = content.trim();
    if (!trimmed) return false;
    if (date && !Number.isFinite(date.getTime())) {
      reportError("todos.error_due");
      return false;
    }
    const dueIso = date ? toDueAtIso(date) : null;
    if (dueIso && dueIso !== todo.due_at) {
      await askForAlerts(dueIso);
      if (!canAct()) return false;
    }
    const recurrenceRule = dueIso ? recurrence : null;
    const nextTopic = topic.trim() || DEFAULT_TOPIC;
    const saved = await mutateRow(todo.id, (snapshot) => ({
      ...snapshot,
      content: trimmed,
      topic: nextTopic,
      due_at: dueIso,
      recurrence_rule: recurrenceRule,
      // A new time's reminder instant is the server's to work out: no alert until it answers.
      notify_at: dueIso === snapshot.due_at ? snapshot.notify_at : null,
    }),
      () => api.updateTodo(token, todo.id, {
        content: trimmed,
        topic: nextTopic,
        due_at: dueIso,
        recurrence_rule: recurrenceRule,
      }), "todos.error_update");
    if (saved && closeOnSave && editorRef.current.value?.id === todo.id) setEditingTodo(null);
    return saved;
  }, [token, canAct, owner, reportError, mutateRow, setEditingTodo, askForAlerts]);

  const handleMarkDone = useCallback(async (ids: string[]) => {
    if (!token) return;
    for (const id of ids) {
      const current = latestTodo(id);
      if (!current || current.checked) continue;
      await mutateRow(id, (snapshot) => ({
        ...snapshot,
        checked: true,
        updated_at: new Date().toISOString(),
      }), () => api.updateTodo(token, id, { checked: true }), "todos.error_update", "toggle");
    }
  }, [token, latestTodo, mutateRow]);

  const handleDeleteMany = useCallback(async (ids: string[]) => {
    if (!token) return;
    let deletedAll = ids.length > 0;
    for (const id of ids) {
      const deleted = await mutateRow(id, () => null, async () => {
        await api.deleteTodo(token, id);
        return null;
      }, "todos.error_delete");
      deletedAll &&= deleted;
    }
    // One haptic for the batch; a failure already says so.
    if (deletedAll) notifyDestructive();
  }, [token, mutateRow]);

  return {
    togglingId: owner.mutations.togglingIds.values().next().value ?? null,
    busyTodoIds: new Set(owner.mutations.pendingIds),
    editingTodo,
    savingTodo: owner.mutations.createId !== null,
    handleCreateTodo,
    handleToggle,
    handleDeleteItem,
    openTodoEditor,
    closeTodoEditor,
    handleUpdateTodo,
    handleMarkDone,
    handleDeleteMany,
  };
}
