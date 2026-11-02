import { act, renderHook } from "@testing-library/react-native";

import { applySavedRows, useReminderProposal } from "@/features/todos/hooks/useReminderProposal";
import { api, type Todo } from "@/lib/api";
import { notifyDestructive, notifyError, notifySuccess, tap } from "@/lib/haptics";

jest.mock("@/lib/api", () => ({ api: { confirmReminderProposal: jest.fn() } }));
jest.mock("@/lib/haptics", () => ({
  tap: jest.fn(),
  notifySuccess: jest.fn(),
  notifyError: jest.fn(),
  notifyDestructive: jest.fn(),
}));
jest.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ token: "tok" }) }));
const mockTodos = { setTodos: jest.fn(), refresh: jest.fn(async () => undefined) };
jest.mock("@/features/todos/context/TodosContext", () => ({ useTodosOptional: () => mockTodos }));
jest.mock("@/features/todos/model/reminderProposal", () => ({
  ...jest.requireActual("@/features/todos/model/reminderProposal"),
  isProposalSaved: () => false,
  markProposalSaved: jest.fn(),
}));
const mockOrder: string[] = [];
const mockAllowAlerts = jest.fn(async () => {
  mockOrder.push("ask");
  return "on" as "on" | "off";
});
jest.mock("@/features/todos/model/reminderAlerts", () => ({
  allowReminderAlerts: () => mockAllowAlerts(),
}));

const row = (id: string, content = id): Todo => ({
  id,
  content,
  topic: "General",
  checked: false,
  due_at: null,
  sort_order: null,
  chat_id: null,
  created_at: "2026-01-01T00:00:00.000Z",
  updated_at: "2026-01-01T00:00:00.000Z",
  notify_at: null,
});
const proposal = {
  proposalId: "p1",
  items: [{ action: "add", title: "Call mom" }],
} as Parameters<typeof useReminderProposal>[0];
const dated = (action: string) =>
  ({
    proposalId: "p2",
    items: [{ action, title: "Stretch", dueAt: "2026-10-24T06:03:00Z" }],
  }) as unknown as Parameters<typeof useReminderProposal>[0];

beforeEach(() => {
  jest.clearAllMocks();
  mockOrder.length = 0;
});

it("puts saved rows in place, adds new ones first and drops deleted ones", () => {
  const rows = [row("a"), row("b"), row("c")];
  expect(applySavedRows(rows, [row("b", "B moved"), row("new")], ["c"]).map((r) => r.content))
    .toEqual(["new", "a", "B moved"]);
});

it("applies the rows a tap saved instead of reading the list again (NET-16)", async () => {
  jest.mocked(api.confirmReminderProposal).mockResolvedValue({ items: [], todos: [row("new")], deleted_ids: [] });
  const { result } = await renderHook(() => useReminderProposal(proposal));
  await act(async () => { await result.current.confirm(); });
  expect(mockTodos.setTodos).toHaveBeenCalledTimes(1);
  const update = mockTodos.setTodos.mock.calls[0][0] as (rows: Todo[]) => Todo[];
  expect(update([row("a")]).map((r) => r.id)).toEqual(["new", "a"]);
  expect(mockTodos.refresh).not.toHaveBeenCalled();
});

it("reads the list when another device saved the card first", async () => {
  jest.mocked(api.confirmReminderProposal).mockResolvedValue({ items: [], todos: null, deleted_ids: [] });
  const { result } = await renderHook(() => useReminderProposal(proposal));
  await act(async () => { await result.current.confirm(); });
  expect(mockTodos.refresh).toHaveBeenCalledWith({ silent: true, force: true });
  expect(mockTodos.setTodos).not.toHaveBeenCalled();
});

describe("asking for alerts when a dated reminder is saved", () => {
  it("asks before the saved rows land, so the reminder sync can schedule", async () => {
    jest.mocked(api.confirmReminderProposal).mockResolvedValue({ items: [], todos: [row("new")], deleted_ids: [] });
    mockTodos.setTodos.mockImplementation(() => {
      mockOrder.push("rows");
    });
    const { result } = await renderHook(() => useReminderProposal(dated("add")));
    await act(async () => { await result.current.confirm(); });
    expect(mockOrder).toEqual(["ask", "rows"]);
    expect(result.current.alertsOff).toBe(false);
  });

  it("says alerts are off when the user said no", async () => {
    jest.mocked(api.confirmReminderProposal).mockResolvedValue({ items: [], todos: [], deleted_ids: [] });
    mockAllowAlerts.mockResolvedValueOnce("off");
    const { result } = await renderHook(() => useReminderProposal(dated("add")));
    await act(async () => { await result.current.confirm(); });
    expect(result.current.alertsOff).toBe(true);
  });

  it("does not ask for a delete, or a reminder with no time", async () => {
    jest.mocked(api.confirmReminderProposal).mockResolvedValue({ items: [], todos: [], deleted_ids: [] });
    const { result } = await renderHook(() => useReminderProposal(dated("delete")));
    await act(async () => { await result.current.confirm(); });
    const undated = await renderHook(() => useReminderProposal(proposal));
    await act(async () => { await undated.result.current.confirm(); });
    expect(mockAllowAlerts).not.toHaveBeenCalled();
  });
});

const haptics = [tap, notifySuccess, notifyError, notifyDestructive];
const hapticCount = () => haptics.reduce((sum, fn) => sum + jest.mocked(fn).mock.calls.length, 0);

it.each([
  ["a saved reminder", "add", notifySuccess],
  ["a confirmed delete", "delete", notifyDestructive],
] as const)("confirms %s with one haptic once it is saved", async (_name, action, played) => {
  jest.mocked(api.confirmReminderProposal).mockResolvedValue({ items: [], todos: [], deleted_ids: [] });
  const card = { ...proposal, items: [{ action, title: "Call mom" }] } as typeof proposal;
  const { result } = await renderHook(() => useReminderProposal(card));
  await act(async () => { await result.current.confirm(); });
  expect(played).toHaveBeenCalledTimes(1);
  expect(hapticCount()).toBe(1);
  // A second tap on a saved card does nothing.
  await act(async () => { await result.current.confirm(); });
  expect(hapticCount()).toBe(1);
});

it("sends one save for two taps before the card re-renders", async () => {
  let answer!: (value: { items: never[]; todos: Todo[]; deleted_ids: string[] }) => void;
  jest.mocked(api.confirmReminderProposal).mockReturnValue(new Promise((resolve) => { answer = resolve; }));
  const { result } = await renderHook(() => useReminderProposal(proposal));
  await act(async () => {
    void result.current.confirm();
    void result.current.confirm();
  });
  await act(async () => { answer({ items: [], todos: [], deleted_ids: [] }); });
  expect(api.confirmReminderProposal).toHaveBeenCalledTimes(1);
  expect(result.current.done).toBe(true);
  expect(result.current.error).toBeNull();
});

it("lets a failed save be tapped again", async () => {
  jest.mocked(api.confirmReminderProposal)
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce({ items: [], todos: [], deleted_ids: [] });
  const { result } = await renderHook(() => useReminderProposal(proposal));
  await act(async () => { await result.current.confirm(); });
  expect(result.current.error).toBe("failed");
  await act(async () => { await result.current.confirm(); });
  expect(api.confirmReminderProposal).toHaveBeenCalledTimes(2);
  expect(result.current.done).toBe(true);
  expect(result.current.error).toBeNull();
});

it("says a failed save with a haptic and no success", async () => {
  jest.mocked(api.confirmReminderProposal).mockRejectedValue(Object.assign(new Error("gone"), { status: 410 }));
  const { result } = await renderHook(() => useReminderProposal(proposal));
  await act(async () => { await result.current.confirm(); });
  expect(result.current.error).toBe("expired");
  expect(notifyError).toHaveBeenCalledTimes(1);
  expect(notifySuccess).not.toHaveBeenCalled();
});
