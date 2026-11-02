import { render } from "@testing-library/react-native";

import { HomeStarters } from "@/features/home/components/HomeStarters";

// The overdue row reads the to-do context's `now` (useReminderClock), not the moment the
// to-dos last changed: a reminder that falls due while the app is open shows on Home.
let mockTodos: { id: string; content: string; due_at: string; checked: boolean; notify_at?: string }[] = [
  {
    id: "todo-1",
    content: "Start anatomy study session",
    due_at: "2026-10-24T12:05:00.000Z",
    checked: false,
  },
];
let mockNow = new Date("2026-10-24T12:00:00.000Z");

jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { id: "user-1", name: "Bini", reminder_lead_minutes: 10 },
  }),
}));
jest.mock("@/features/todos/context/TodosContext", () => ({
  useTodos: () => ({
    todos: mockTodos,
    loading: false,
    remindersReady: true,
    homeNudgeDismissed: new Set<string>(),
    dismissReminderNudge: jest.fn(),
    now: mockNow,
  }),
}));
jest.mock("@/features/home/model/homeWelcome", () => ({
  homeGreeting: () => "Good afternoon",
}));
jest.mock("@/lib/haptics", () => ({ tap: jest.fn() }));
jest.mock("@/features/todos/model/dueDate", () => ({
  describeDueAt: () => ({ label: "Overdue today", tone: "overdue" }),
}));
jest.mock("@/features/todos/model/homeReminderNudges", () => ({
  filterHomeNudgeTodos: (todos: unknown[]) => todos,
}));
jest.mock("expo-router", () => ({ useRouter: () => ({ push: jest.fn() }) }));

it("shows a reminder as overdue once the clock passes its due time", async () => {
  const view = await render(<HomeStarters composerActive={false} />);
  expect(await view.findByText("Good afternoon")).toBeTruthy();
  expect(view.queryByText("Start anatomy study session")).toBeNull();

  mockNow = new Date("2026-10-24T12:06:00.000Z");
  await view.rerender(<HomeStarters composerActive={false} />);

  expect(await view.findByText("Start anatomy study session")).toBeTruthy();
});

it("shows an overdue reminder from its notify_at, after quiet hours, as push does", async () => {
  // Quiet hours 22:00-07:00: due at 23:30, the server sends its reminder at 07:00.
  mockTodos = [{
    id: "todo-2", content: "Call Sam", due_at: "2026-10-24T23:30:00.000Z", checked: false,
    notify_at: "2026-10-25T07:00:00.000Z",
  }];
  mockNow = new Date("2026-10-24T23:45:00.000Z");
  const view = await render(<HomeStarters composerActive={false} />);
  expect(await view.findByText("Good afternoon")).toBeTruthy();
  expect(view.queryByText("Call Sam")).toBeNull();

  mockNow = new Date("2026-10-25T07:00:00.000Z");
  await view.rerender(<HomeStarters composerActive={false} />);
  expect(await view.findByText("Call Sam")).toBeTruthy();
});
