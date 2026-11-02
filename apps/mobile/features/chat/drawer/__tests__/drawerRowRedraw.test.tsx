/**
 * What redraws the drawer's chat rows. FlashList redraws a cell only when its item,
 * renderItem or extraData changes, and a memoized row only when one of its props does.
 * Typing in the search redraws none of them: every keystroke used to change renderItem
 * (the new search's result handlers) and the list's items (a new empty result list).
 */
import { act, fireEvent, render } from "@testing-library/react-native";

import { ConversationList } from "@/features/chat/drawer/ConversationList";
import type { DrawerChatListItem } from "@/features/chat/drawer/DrawerChatFlashList";
import { api, type Chat } from "@/lib/api";

type ListProps = { data: DrawerChatListItem[]; renderItem: unknown; extraData?: unknown };
const mockLists: ListProps[] = [];
const mockRouter = { setParams: jest.fn(), push: jest.fn() };
const mockUser = { id: "u1", name: "Ann", email: "a@b.c", plan: "free" };
const mockChat = (i: number): Chat => ({ id: `chat-${i}`, title: `Chat ${i}`, pinned: i < 3, archived: false,
  created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", model: "auto" } as Chat);
const mockGroups = { pinned: [0, 1, 2].map(mockChat), today: Array.from({ length: 40 }, (_, i) => mockChat(i + 3)),
  yesterday: [], last_7_days: [], this_month: [], older: [], archived: [] };
const mockAllChats = [...mockGroups.pinned, ...mockGroups.today];

jest.mock("@shopify/flash-list", () => ({ FlashList: (props: ListProps) => { mockLists.push(props); return null; } }));
jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => 0 }));
jest.mock("@/contexts/AuthContext", () => ({ useAuthToken: () => "token", useAuth: () => ({ user: mockUser, token: "token" }) }));
jest.mock("@/contexts/DrawerContext", () => ({ useDrawerOpen: () => true }));
jest.mock("expo-router", () => ({ useRouter: () => mockRouter }));
jest.mock("expo-linear-gradient", () => ({ LinearGradient: () => null }));
jest.mock("@/lib/api", () => ({ api: { search: jest.fn() } }));
jest.mock("@/features/attachments/model/galleryListCache", () => ({ prefetchGallery: jest.fn() }));
jest.mock("@/features/todos/hooks/useReminderBadgeCount", () => ({ useReminderBadgeCount: () => ({}) }));
jest.mock("@/features/chat/hooks/useChatBulkActions", () => ({ useChatBulkActions: () => ({}) }));
jest.mock("@/features/chat/hooks/useChatMenuActions", () => ({ useChatMenuActions: () => ({}) }));
jest.mock("@/features/chat/drawer/useDrawerChatList", () => {
  const noop = () => undefined;
  const collapsed = () => false;
  return { useDrawerChatList: () => ({ groups: mockGroups, allChats: mockAllChats, load: noop, loading: false,
    error: false, refreshing: false, isSectionCollapsed: collapsed, toggleSectionCollapsed: noop }) };
});

beforeEach(() => {
  jest.useFakeTimers();
  jest.mocked(api.search).mockResolvedValue({ items: [], next_cursor: null });
});
afterEach(() => { jest.useRealTimers(); });

it("keeps every chat row's item and the renderItem while the search is typed", async () => {
  const ui = await render(<ConversationList />);
  await fireEvent.press(ui.getByLabelText("search.open_accessibility"));
  await act(async () => { jest.advanceTimersByTime(50); });
  const before = mockLists.at(-1)!;
  expect(before.data.filter((item) => item.type === "row")).toHaveLength(43);
  for (const query of ["p", "pi", "piz", "pizz", "pizza"]) {
    await fireEvent.changeText(ui.getByPlaceholderText("search.placeholder"), query);
  }
  const after = mockLists.at(-1)!;
  expect(after.renderItem).toBe(before.renderItem);
  expect(after.extraData).toBe(before.extraData);
  expect(after.data).toHaveLength(before.data.length);
  after.data.forEach((item, index) => expect(item).toBe(before.data[index]));
});

// The select handler is renewed with each selection and each drawer open; a row only
// calls it while selecting. Handing it to rows outside selection redrew every row a
// second time on each open and close (15 rows -> 30 renders per open, 1,000 chats).
it("hands rows the select handler only while selecting", async () => {
  await render(<ConversationList />);
  const { data, renderItem } = mockLists.at(-1)!;
  const row = data.find((item) => item.type === "row")!;
  const element = (renderItem as (info: { item: DrawerChatListItem }) => { props: Record<string, unknown> })({ item: row });
  expect(element.props.selectionMode).toBe(false);
  expect(element.props.onToggleSelect).toBeUndefined();
  expect(element.props.onOpen).toEqual(expect.any(Function));
});
