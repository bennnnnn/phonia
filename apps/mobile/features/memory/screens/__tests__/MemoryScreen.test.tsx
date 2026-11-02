import { act, fireEvent, render, within } from "@testing-library/react-native";

import MemoryScreen from "@/features/memory/screens/MemoryScreen";
import type { MemoryDocument } from "@/features/memory/types";

let mockToken: string | null = "token-a";
const mockLoad = jest.fn(async () => {});
const mockInstruct = jest.fn();
const mockFeedback = { error: jest.fn(), success: jest.fn(), warning: jest.fn() };
const mockRouter = { push: jest.fn(), replace: jest.fn() };
let mockDocuments: MemoryDocument[] = [];
let mockScanning = false;
let mockLoading = false;
let mockError = false;

jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => 1 }));
const mockClearAll = jest.fn(async () => true);
jest.mock("@/features/memory/hooks/useClearAllMemories", () => ({
  useClearAllMemories: () => ({ clearAll: mockClearAll, busy: false }),
}));
jest.mock("@/features/memory/components/MemoryHeaderMenu", () => {
  const { Pressable, Text } = jest.requireActual("react-native") as typeof import("react-native");
  return {
    MemoryHeaderMenu: ({
      items,
    }: {
      items: { key: string; label: string; onPress: () => void; testID?: string }[];
    }) =>
      items.map((item) => (
        <Pressable key={item.key} testID={item.testID ?? `menu-${item.key}`} onPress={item.onPress}>
          <Text>{item.label}</Text>
        </Pressable>
      )),
  };
});
jest.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ token: mockToken }) }));
jest.mock("@/contexts/actionFeedbackCore", () => ({ useActionFeedbackOptional: () => mockFeedback }));
jest.mock("@/lib/reportRecoverableError", () => ({
  reportRecoverableError: (_feedback: unknown, message: string) => mockFeedback.error(message),
}));
jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { date?: string }) =>
      options?.date ? `${key}:${options.date}` : key,
    i18n: { language: "en" },
  }),
}));
jest.mock("@/lib/theme", () => ({ useTheme: () => ({}) }));
jest.mock("@/ui/icons/Icon", () => ({ Icon: () => null }));
jest.mock("@/ui/feedback/SkeletonLoader", () => ({ SkeletonList: () => null }));
jest.mock("@/ui/feedback/StateView", () => ({
  StateView: ({ title, onRetry }: { title: string; onRetry?: () => void }) => {
    const { Text } = jest.requireActual("react-native");
    return <Text onPress={onRetry}>{title}</Text>;
  },
}));
jest.mock("expo-router", () => ({
  Redirect: () => null,
  useRouter: () => mockRouter,
  useFocusEffect: (effect: () => void | (() => void)) => {
    const React = jest.requireActual("react");
    React.useEffect(() => effect(), [effect]);
  },
}));
jest.mock("@/features/memory/hooks/useMemoryDocuments", () => ({
  useMemoryDocuments: () => ({
    documents: mockDocuments,
    scanning: mockScanning,
    loading: mockLoading,
    error: mockError,
    load: mockLoad,
    instruct: mockInstruct,
  }),
}));

function doc(key: string, group: MemoryDocument["group"], title: string, updated_at: string | null = null) {
  return { key, group, title, summary: `${title} summary`, updated_at, facts: [] };
}

beforeEach(() => {
  jest.clearAllMocks();
  mockToken = "token-a";
  mockScanning = false;
  mockLoading = false;
  mockError = false;
  mockDocuments = [
    doc("area:recall", "areas", "Recall", "2026-08-30T12:00:00Z"),
    doc("profile", "you", "Profile"),
    doc("tech-stack", "topics", "Tech stack"),
    doc("preferences", "you", "Preferences"),
  ];
});

describe("MemoryScreen", () => {
  it("clears all memories from the menu at the top right, then reloads", async () => {
    const ui = await render(<MemoryScreen />);
    mockLoad.mockClear();
    await act(async () => {
      fireEvent.press(ui.getByTestId("menu-clear-all"));
    });
    expect(mockClearAll).toHaveBeenCalled();
    expect(ui.getByText("settings.memory_clear_all")).toBeTruthy();
    expect(mockLoad).toHaveBeenCalled();
  });

  it("lists You, Topics and Areas pages and loads on open", async () => {
    const ui = await render(<MemoryScreen />);

    expect(mockLoad).toHaveBeenCalled();
    const you = within(ui.getByTestId("memory-group-you"));
    // Standard pages use the app's words; sorted by the shown title.
    const youTitles = you.getAllByText(/memory\.doc\..*\.title/).map((node) => node.props.children);
    expect(youTitles).toEqual(["memory.doc.preferences.title", "memory.doc.profile.title"]);
    expect(within(ui.getByTestId("memory-group-topics")).getByText("memory.doc.tech-stack.title")).toBeTruthy();
    const areas = within(ui.getByTestId("memory-group-areas"));
    expect(areas.getByText("Recall")).toBeTruthy();
    expect(areas.getByText("Recall summary")).toBeTruthy();
    expect(ui.getByLabelText(/^Recall, memory\.updated:/)).toBeTruthy();
  });

  it("opens a page", async () => {
    const ui = await render(<MemoryScreen />);
    await fireEvent.press(ui.getByTestId("memory-document-area:recall"));
    expect(mockRouter.push).toHaveBeenCalledWith({
      pathname: "/memory/[key]",
      params: { key: "area:recall" },
    });
  });

  it("sends a plain-words edit and shows the reply", async () => {
    mockInstruct.mockResolvedValue({ ok: true, reply: "Saved: disagree more.", applied: 1, dropped: 0 });
    const ui = await render(<MemoryScreen />);

    await fireEvent.changeText(ui.getByTestId("memory-composer-input"), "  You can disagree with me more ");
    await fireEvent.press(ui.getByTestId("memory-composer-send"));

    expect(mockInstruct).toHaveBeenCalledWith("You can disagree with me more", undefined);
    expect(mockFeedback.success).toHaveBeenCalledWith("Saved: disagree more.");
    expect(ui.getByTestId("memory-composer-input").props.value).toBe("");
  });

  it("warns and keeps the words when the edit changed nothing", async () => {
    // The model said "Added your goal." but its edit never landed.
    mockInstruct.mockResolvedValue({ ok: true, reply: "Added your goal.", applied: 0, dropped: 1 });
    const ui = await render(<MemoryScreen />);

    await fireEvent.changeText(ui.getByTestId("memory-composer-input"), "My goal is a marathon");
    await fireEvent.press(ui.getByTestId("memory-composer-send"));

    expect(mockFeedback.success).not.toHaveBeenCalled();
    expect(mockFeedback.warning).toHaveBeenCalledWith("memory.instruct_nothing");
    expect(ui.getByTestId("memory-composer-input").props.value).toBe("My goal is a marathon");
  });

  it("keeps the words and says so when the edit fails", async () => {
    mockInstruct.mockResolvedValue({ ok: false, failure: "failed" });
    const ui = await render(<MemoryScreen />);

    await fireEvent.changeText(ui.getByTestId("memory-composer-input"), "Keep it short");
    await fireEvent.press(ui.getByTestId("memory-composer-send"));

    expect(mockFeedback.error).toHaveBeenCalledWith("memory.instruct_failed");
    expect(ui.getByTestId("memory-composer-input").props.value).toBe("Keep it short");
  });

  it.each([
    ["off", "memory.off"],
    // The day's spend cap said "Memory couldn't be updated. Try again.", which fails all day.
    ["paused", "memory.paused"],
    // Redis down (the spend read, the write lock) said "couldn't be updated" or "being updated".
    ["unavailable", "common.service_unavailable"],
  ])("says why an edit was refused: %s (CLAR-08)", async (failure, line) => {
    mockInstruct.mockResolvedValue({ ok: false, failure });
    const ui = await render(<MemoryScreen />);

    await fireEvent.changeText(ui.getByTestId("memory-composer-input"), "Keep it short");
    await fireEvent.press(ui.getByTestId("memory-composer-send"));

    expect(mockFeedback.error).toHaveBeenCalledWith(line);
  });

  it("says when it is reading recent chats", async () => {
    mockScanning = true;
    mockDocuments = [];
    const ui = await render(<MemoryScreen />);
    expect(ui.getByTestId("memory-scanning")).toBeTruthy();
    expect(ui.queryByText("memory.empty_title")).toBeNull();
  });

  it("shows the empty state and starts a chat from it", async () => {
    mockDocuments = [];
    const ui = await render(<MemoryScreen />);
    await fireEvent.press(ui.getByText("memory.empty_title"));
    expect(mockRouter.replace).toHaveBeenCalledWith("/");
  });

  it("retries after an error", async () => {
    mockError = true;
    mockDocuments = [];
    const ui = await render(<MemoryScreen />);
    mockLoad.mockClear();
    await fireEvent.press(ui.getByText("common.error"));
    expect(mockLoad).toHaveBeenCalledTimes(1);
  });
});
