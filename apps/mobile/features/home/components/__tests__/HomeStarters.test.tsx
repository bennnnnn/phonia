import { StyleSheet } from "react-native";
import { act, fireEvent, render } from "@testing-library/react-native";

import { HomeStarters } from "@/features/home/components/HomeStarters";
import { AA, compositeOver, contrastRatio } from "@/lib/__tests__/support/contrast";
import { ACCENT_OPTIONS, DEFAULT_ACCENT } from "@/lib/accent";
import { setAccentSnapshot } from "@/lib/accentRuntime";
import { themeFor } from "@/lib/theme";

let mockOverdue: { id: string; content: string; due_at: string } | undefined;
let mockScheme: "light" | "dark" = "light";

jest.mock("@/lib/colorScheme", () => ({ useResolvedColorScheme: () => mockScheme }));

jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { id: "user-1", reminder_lead_minutes: 15 } }),
}));
jest.mock("@/features/todos/context/TodosContext", () => ({
  useTodos: () => ({
    todos: [],
    loading: false,
    remindersReady: true,
    homeNudgeDismissed: {},
    dismissReminderNudge: jest.fn(),
  }),
}));
jest.mock("@/features/home/model/homeWelcome", () => ({
  homeGreeting: () => "Good morning",
}));
jest.mock("@/lib/haptics", () => ({ tap: jest.fn() }));
jest.mock("@/features/todos/model/dueDate", () => ({
  describeDueAt: () => ({ label: "2d overdue", tone: "overdue" }),
}));
jest.mock("@/features/todos/model/homeReminderNudges", () => ({
  filterHomeNudgeTodos: (todos: unknown[]) => todos,
}));
jest.mock("@/features/todos/model/homeUrgentTodos", () => ({
  firstOverdueHomeTodo: () => mockOverdue,
  listHomeUrgentTodos: () => [],
}));
jest.mock("expo-router", () => ({ useRouter: () => ({ push: jest.fn() }) }));

beforeEach(() => {
  mockOverdue = undefined;
  jest.clearAllMocks();
});

afterEach(async () => {
  mockScheme = "light";
  await act(async () => setAccentSnapshot(DEFAULT_ACCENT));
});

it("shows the greeting without starter chips", async () => {
  const view = await render(<HomeStarters composerActive={false} />);
  expect(await view.findByText("Good morning")).toBeTruthy();
  expect(view.queryByText("Help me think")).toBeNull();
  expect(view.queryByText("What can you do?")).toBeNull();
});

it("hides the greeting while the composer is in use", async () => {
  const view = await render(<HomeStarters composerActive={false} />);
  expect(await view.findByText("Good morning")).toBeTruthy();

  await view.rerender(<HomeStarters composerActive />);

  expect(view.queryByText("Good morning")).toBeNull();
});

it("keeps one overdue reminder", async () => {
  mockOverdue = {
    id: "todo-1",
    content: "Pay rent",
    due_at: "2026-07-01T12:00:00.000Z",
  };
  const view = await render(<HomeStarters composerActive={false} />);
  expect(await view.findByText("Pay rent")).toBeTruthy();
  expect(view.getByText("chat.home.overdue")).toBeTruthy();
  await act(async () => {
    fireEvent.press(view.getByLabelText("chat.home.dismiss_reminder"));
  });
});

/** WCAG 1.4.11: an icon that carries meaning needs 3:1 on its plane. */
const NON_TEXT = 3;

// Red like the to-do row's overdue time and mark. Its heading sits on the chat page (bg);
// the rest on the card's own fill, laid over that page.
it.each(["light", "dark"] as const)(
  "%s: the overdue card is danger, AA for its text and 3:1 for its icons, in every accent",
  async (scheme) => {
    mockScheme = scheme;
    mockOverdue = { id: "todo-1", content: "Pay rent", due_at: "2026-07-01T12:00:00.000Z" };
    const failures: string[] = [];
    for (const accent of ACCENT_OPTIONS) {
      await act(async () => setAccentSnapshot(accent));
      const C = themeFor(scheme, accent);
      const ui = await render(<HomeStarters composerActive={false} />);
      const card = ui.getByLabelText("Pay rent");
      const cardStyle = StyleSheet.flatten(card.props.style);
      const plane = compositeOver(String(cardStyle.backgroundColor), C.bg);
      const ink = (node: ReturnType<typeof ui.getByText>) => String(StyleSheet.flatten(node.props.style).color);
      const heading = ink(ui.getByText("chat.home.overdue"));
      const due = ink(ui.getByText("2d overdue"));
      const icons = card.queryAll((node) => typeof node.props.name === "string");
      expect({ accent, heading, due, border: cardStyle.borderColor, icons: icons.map((icon) => icon.props.color) })
        .toEqual({ accent, heading: C.danger, due: C.danger, border: C.danger, icons: [C.danger, C.danger] });
      const pairs: [string, string, string, number][] = [
        ["heading", heading, C.bg, AA],
        ["title", ink(ui.getByText("Pay rent")), plane, AA],
        ["due", due, plane, AA],
        ...icons.map((icon): [string, string, string, number] => [icon.props.name, icon.props.color, plane, NON_TEXT]),
      ];
      for (const [what, fg, bg, floor] of pairs) {
        const ratio = contrastRatio(fg, bg);
        if (ratio < floor) failures.push(`${accent} ${what} ${ratio.toFixed(2)}`);
      }
      await ui.unmount();
    }
    expect(failures).toEqual([]);
  },
);
