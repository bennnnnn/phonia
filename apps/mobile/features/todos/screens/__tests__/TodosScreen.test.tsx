import { act, render } from "@testing-library/react-native";
import TodosScreen from "@/features/todos/screens/TodosScreen";

let mockSession = 1;
let mockToken: string | null = "token-a";
let mockFocused = true;
let mockRouteParams: Record<string, string> = {};
const mockRefresh = jest.fn(async () => {});
const mockNavigation = { setOptions: jest.fn() };
let mockAdd: { onPress: () => void };
let mockSheet: {
  visible: boolean;
  onClose: () => void;
  onSave: (content: string, due: Date | null, recurrence: null, topic: string) => void;
};
let mockList: {
  onRefresh: () => Promise<void>; refreshing: boolean; rows: unknown[];
  onOpen: (row: { id: string; content: string }) => void; onSelect: (row: { id: string }) => void;
};
let mockHeader: { onRetry: () => void };
const mockOpenTodo = jest.fn();
const mockCreate = jest.fn();
const mockInfo = jest.fn();
const mockGetTodos = () => mockTodos;
let mockTodos: {
  id: string;
  content: string;
  checked: boolean;
  due_at: string | null;
  topic: string;
  sort_order: null;
  chat_id: null;
  created_at: string;
  updated_at: string;
}[] = [];
const mockCurrentSession = () => true;
const mockMarkSeenIds = jest.fn(async () => {});
let mockActionParams: { isCurrentView: () => boolean; getTodos: () => unknown; markSeenIds: unknown };

jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => mockSession }));
jest.mock("@/contexts/AuthContext", () => {
  const React = jest.requireActual("react");
  const Context = React.createContext(0);
  return { TestAuthProvider: Context.Provider, useAuth: () => {
    React.useContext(Context);
    return { token: mockToken, user: { id: "user" } };
  } };
});
jest.mock("expo-router", () => ({
  Redirect: () => null,
  useNavigation: () => mockNavigation,
  useLocalSearchParams: () => mockRouteParams,
  useFocusEffect: (effect: () => void | (() => void)) => {
    const React = jest.requireActual("react");
    const focused = mockFocused;
    React.useEffect(() => focused ? effect() : undefined, [effect, focused]);
  },
}));
jest.mock("react-native-gesture-handler", () => ({ GestureHandlerRootView: ({ children }: { children: React.ReactNode }) => children }));
jest.mock("@/lib/i18n", () => ({
  __esModule: true,
  default: { t: (key: string) => key },
  ensureLocale: jest.fn(),
}));
jest.mock("@/lib/theme", () => ({ useTheme: () => ({}) }));
jest.mock("@/ui/feedback/SkeletonLoader", () => ({ SkeletonList: () => null }));
jest.mock("@/ui/controls/AddFab", () => ({ AddFab: (props: typeof mockAdd) => { mockAdd = props; return null; } }));
jest.mock("@/features/todos/components/TodoEditorSheet", () => ({
  TodoEditorSheet: (props: typeof mockSheet & { editTodo?: unknown }) => {
    // The screen renders two instances: the add sheet (no editTodo prop) and
    // the edit sheet (editTodo, possibly null). Tests observe the add sheet.
    if (!("editTodo" in props)) mockSheet = props;
    return null;
  },
}));
jest.mock("@/features/todos/components/TodosScrollList", () => ({ TodosScrollList: (props: typeof mockList & { listHeader: React.ReactNode }) => { mockList = props; return props.listHeader; } }));
jest.mock("@/features/todos/components/TodosListHeader", () => ({ TodosListHeader: (props: typeof mockHeader) => { mockHeader = props; return null; } }));
jest.mock("@/features/todos/hooks/useTodosActions", () => ({ useTodosActions: (params: typeof mockActionParams) => {
  mockActionParams = params;
  return {
    busyTodoIds: new Set(),
    editingTodo: null,
    savingTodo: false,
    handleToggle: jest.fn(),
    openTodoEditor: mockOpenTodo,
    handleDeleteItem: jest.fn(),
    closeTodoEditor: jest.fn(),
    handleCreateTodo: mockCreate,
    handleUpdateTodo: jest.fn(),
  };
} }));
jest.mock("@/contexts/actionFeedbackCore", () => ({ useActionFeedbackOptional: () => ({ info: mockInfo }) }));
jest.mock("@/features/todos/context/TodosContext", () => ({ useTodos: () => ({ todos: mockTodos, loading: false, error: false,
  getTodos: mockGetTodos, isCurrentSession: mockCurrentSession, markSeenIds: mockMarkSeenIds,
  refresh: mockRefresh, setTodos: jest.fn(),
}) }));

beforeEach(() => {
  jest.clearAllMocks(); mockSession++; mockToken = "token-a"; mockFocused = true;
  mockRouteParams = {}; mockTodos = [];
  mockRefresh.mockResolvedValue();
});

it("closes the reminder draft on a context-only account change", async () => {
  const { TestAuthProvider } = jest.requireMock("@/contexts/AuthContext");
  const screen = <TodosScreen />;
  const ui = await render(<TestAuthProvider value={1}>{screen}</TestAuthProvider>);
  await act(() => { mockAdd.onPress(); });
  expect(mockSheet.visible).toBe(true);
  const oldOwner = mockActionParams.isCurrentView;
  mockSession++; mockToken = "token-b";
  await ui.rerender(<TestAuthProvider value={2}>{screen}</TestAuthProvider>);
  expect(mockSheet.visible).toBe(false);
  expect(oldOwner()).toBe(false);
  expect(mockActionParams.isCurrentView()).toBe(true);
});

it("keeps the draft open through a normal access-token refresh", async () => {
  const ui = await render(<TodosScreen />);
  await act(() => { mockAdd.onPress(); });
  mockToken = "refreshed-token";
  await ui.rerender(<TodosScreen />);
  expect(mockSheet.visible).toBe(true);
  expect(mockActionParams.getTodos).toBe(mockGetTodos);
  expect(mockActionParams.markSeenIds).toBe(mockMarkSeenIds);
});

it.each(["account", "blur", "unmount"])("ignores retained Add and Retry callbacks after %s", async (change) => {
  const ui = await render(<TodosScreen />);
  const add = mockAdd.onPress;
  const retry = mockHeader.onRetry;
  if (change === "account") mockSession++;
  if (change === "blur") { mockFocused = false; await ui.rerender(<TodosScreen />); }
  if (change === "unmount") await ui.unmount();
  await act(() => { add(); retry(); });
  expect(mockRefresh).not.toHaveBeenCalled();
});

it("closes a draft when leaving To-do and rejects its old close callback on return", async () => {
  const ui = await render(<TodosScreen />);
  await act(() => { mockAdd.onPress(); });
  const close = mockSheet.onClose;
  mockFocused = false; await ui.rerender(<TodosScreen />);
  mockFocused = true; await ui.rerender(<TodosScreen />);
  expect(mockSheet.visible).toBe(false);
  await act(() => { mockAdd.onPress(); close(); });
  expect(mockSheet.visible).toBe(true);
});

it("deduplicates pull refresh before React rerenders", async () => {
  let resolve!: () => void;
  mockRefresh.mockReturnValue(new Promise<void>((done) => { resolve = done; }));
  await render(<TodosScreen />);
  const refresh = mockList.onRefresh;
  let pending!: Promise<void>;
  await act(() => { pending = refresh(); void refresh(); });
  expect(mockList.refreshing).toBe(true);
  expect(mockRefresh).toHaveBeenCalledTimes(1);
  await act(async () => { resolve(); await pending; });
  expect(mockList.refreshing).toBe(false);
});

it("opens a to-do when its row is tapped", async () => {
  await render(<TodosScreen />);
  const todo = { id: "todo-1", content: "Walk" };
  await act(() => { mockList.onOpen(todo); });
  expect(mockOpenTodo).toHaveBeenCalledWith(todo);
});

it("hands every row the same open and select handlers on each render, so a change redraws only its row", async () => {
  mockTodos = [todoAt("a", 0), todoAt("b", 0)];
  const ui = await render(<TodosScreen />);
  const { onOpen, onSelect } = mockList;
  mockTodos = [{ ...mockTodos[0]!, checked: true }, mockTodos[1]!];
  await ui.rerender(<TodosScreen />);
  expect(mockList.onOpen).toBe(onOpen);
  expect(mockList.onSelect).toBe(onSelect);
});

it("opens a plain to-do draft without any scheduling step", async () => {
  await render(<TodosScreen />);
  await act(async () => { mockAdd.onPress(); });
  expect(mockSheet.visible).toBe(true);
});

function todoAt(id: string, dayOffset: number) {
  const due = new Date();
  due.setDate(due.getDate() + dayOffset);
  due.setHours(15, 0, 0, 0);
  return {
    id,
    content: id,
    checked: false,
    due_at: due.toISOString(),
    topic: "General",
    sort_order: null,
    chat_id: null,
    created_at: "2026-09-01T00:00:00.000Z",
    updated_at: "2026-09-01T00:00:00.000Z",
  };
}

it("opens Schedule on overdue and today", async () => {
  mockTodos = [todoAt("later", 14), todoAt("overdue", -1), todoAt("today", 0)];
  await render(<TodosScreen />);
  const ids = (mockList.rows as { kind: string; todo?: { id: string } }[])
    .filter((row) => row.kind === "todo")
    .map((row) => row.todo?.id);
  expect(ids).toEqual(["overdue", "today"]);
});

it("opens the reminder a due notification points at", async () => {
  const due = todoAt("todo-1", 0);
  mockTodos = [due];
  mockRouteParams = { highlight: "todo-1" };
  await render(<TodosScreen />);
  expect(mockOpenTodo).toHaveBeenCalledWith(due);
});


it.each([
  ["a to-do due in three days", 3, true],
  ["a to-do due today", 0, false],
])("after adding %s on Today, says where it went only when Today hides it", async (_name, days, moved) => {
  await render(<TodosScreen />);
  await act(() => { mockAdd.onPress(); });
  const due = new Date();
  due.setDate(due.getDate() + days);
  await act(() => { mockSheet.onSave("Gym", due, null, "General"); });
  const onCreated = mockCreate.mock.calls[0][2] as () => void;
  await act(() => { onCreated(); });
  expect(mockSheet.visible).toBe(false);
  if (moved) expect(mockInfo).toHaveBeenCalledWith("todos.added_shown_open");
  else expect(mockInfo).not.toHaveBeenCalled();
});
