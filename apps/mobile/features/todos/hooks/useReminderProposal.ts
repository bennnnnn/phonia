import { useRef, useState } from "react";

import { useAuth } from "@/contexts/AuthContext";
import { useTodosOptional } from "@/features/todos/context/TodosContext";
import { allowReminderAlerts } from "@/features/todos/model/reminderAlerts";
import {
  isProposalSaved,
  markProposalSaved,
  proposalAction,
  type ReminderProposal,
} from "@/features/todos/model/reminderProposal";
import { api, type Todo } from "@/lib/api";
import { notifyDestructive, notifyError, notifySuccess } from "@/lib/haptics";

type ReminderProposalError = "expired" | "changed" | "failed";

/** `rows` with the saved rows in place (new ones first) and the deleted ones gone. */
export function applySavedRows(rows: Todo[], saved: Todo[], deletedIds: string[]): Todo[] {
  const gone = new Set(deletedIds);
  const byId = new Map(saved.map((row) => [row.id, row]));
  const kept = rows.filter((row) => !gone.has(row.id)).map((row) => byId.get(row.id) ?? row);
  const known = new Set(rows.map((row) => row.id));
  return [...saved.filter((row) => !known.has(row.id)), ...kept];
}

/** Saves a chat reminder card on tap, then refreshes To-do and its notifications. */
export function useReminderProposal(proposal: ReminderProposal) {
  const { token } = useAuth();
  const todos = useTodosOptional();
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(() => isProposalSaved(proposal));
  const [error, setError] = useState<ReminderProposalError | null>(null);
  const [alertsOff, setAlertsOff] = useState(false);
  // State lags a render: two quick taps both saw `busy` false and both sent, and the
  // second's 409 put "That reminder changed" under a card that said Saved.
  const sending = useRef(false);

  const confirm = async () => {
    if (!token || busy || done || sending.current) return;
    sending.current = true;
    setBusy(true);
    setError(null);
    let saved: Awaited<ReturnType<typeof api.confirmReminderProposal>>;
    try {
      saved = await api.confirmReminderProposal(token, proposal.proposalId);
    } catch (caught) {
      // ApiRequestError carries the HTTP status: 410 expired, 409 changed since.
      const status = (caught as { status?: unknown } | null)?.status;
      setError(status === 410 ? "expired" : status === 409 ? "changed" : "failed");
      notifyError();
      sending.current = false;
      setBusy(false);
      return;
    }
    // Saved: nothing after this is the save failing.
    markProposalSaved(proposal.proposalId);
    setDone(true);
    setBusy(false);
    // One haptic for the tap, when the card is saved (a delete, as every delete does).
    if (proposalAction(proposal) === "delete") notifyDestructive();
    else notifySuccess();
    // Ask before the rows land, so the reminder sync that follows may schedule its alert.
    if (proposal.items.some((item) => item.dueAt && (item.action === "add" || item.action === "set_due"))) {
      setAlertsOff((await allowReminderAlerts()) === "off");
    }
    // The rows the tap wrote, applied as they are (code-health audit NET-16); a card
    // another device saved first sends none, and the list is read again.
    if (saved.todos) todos?.setTodos((rows) => applySavedRows(rows, saved.todos ?? [], saved.deleted_ids));
    else void todos?.refresh({ silent: true, force: true });
  };

  return { busy, done: done || isProposalSaved(proposal), error, alertsOff, confirm };
}
