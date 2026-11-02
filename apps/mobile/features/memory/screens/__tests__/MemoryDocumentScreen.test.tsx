import { act, fireEvent, render } from "@testing-library/react-native";

import MemoryDocumentScreen from "@/features/memory/screens/MemoryDocumentScreen";
import type { MemoryDocument } from "@/features/memory/types";

let mockKey = "area:recall";
const mockLoad = jest.fn(async () => {});
const mockInstruct = jest.fn();
const mockDeleteDocument = jest.fn();
const mockDeleteFact = jest.fn();
const mockEditFact = jest.fn();
const mockSetFactMuted = jest.fn();
const mockConfirm = jest.fn(async (..._args: unknown[]) => true);
const mockFeedback = { error: jest.fn(), success: jest.fn(), warning: jest.fn() };
const mockRouter = { back: jest.fn(), push: jest.fn() };
let mockDocuments: MemoryDocument[] = [];
let mockLoading = false;
let mockError = false;

jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => 1 }));
// Each fact drawn reads its text once: the count is how many facts were drawn.
const mockFactsDrawn = { count: 0 };
jest.mock("@/features/memory/model/memoryFacts", () => {
  const actual = jest.requireActual("@/features/memory/model/memoryFacts");
  return {
    ...actual,
    stripMemoryAsOf: (text: string) => {
      mockFactsDrawn.count += 1;
      return actual.stripMemoryAsOf(text);
    },
  };
});
const mockDestructive = jest.fn();
jest.mock("@/lib/haptics", () => ({
  ...jest.requireActual("@/lib/haptics"),
  notifyDestructive: (...args: unknown[]) => mockDestructive(...args),
}));
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
jest.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ token: "token-a" }) }));
jest.mock("@/contexts/actionFeedbackCore", () => ({ useActionFeedbackOptional: () => mockFeedback }));
jest.mock("@/lib/reportRecoverableError", () => ({
  reportRecoverableError: (_feedback: unknown, message: string) => mockFeedback.error(message),
}));
jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { title?: string }) =>
      options?.title ? `${key}:${options.title}` : key,
    i18n: { language: "en" },
  }),
}));
// One palette object, as the real hook keeps (its identity keys the screen's styles).
const mockTheme = {};
jest.mock("@/lib/theme", () => ({ useTheme: () => mockTheme }));
jest.mock("@/ui/icons/Icon", () => ({ Icon: () => null }));
jest.mock("@/ui/feedback/SkeletonLoader", () => ({ SkeletonList: () => null }));
jest.mock("@/ui/feedback/StateView", () => ({
  StateView: ({ title, onRetry }: { title: string; onRetry?: () => void }) => {
    const { Text } = jest.requireActual("react-native");
    return <Text onPress={onRetry}>{title}</Text>;
  },
}));
jest.mock("@/ui/overlay/dialogs", () => ({ confirmDialog: (...args: unknown[]) => mockConfirm(...args) }));
jest.mock("@/ui/overlay/Menu", () => ({
  Menu: ({ visible, items }: { visible: boolean; items: { key: string; label: string; onPress: () => void }[] }) => {
    const { Text, View } = jest.requireActual("react-native");
    if (!visible) return null;
    return (
      <View testID="memory-fact-menu">
        {items.map((item) => (
          <Text key={item.key} onPress={item.onPress} testID={`menu-${item.key}`}>
            {item.label}
          </Text>
        ))}
      </View>
    );
  },
}));
jest.mock("@/ui/overlay/FieldSheet", () => ({
  FieldSheet: ({
    visible,
    value,
    onChangeText,
    onSave,
  }: {
    visible: boolean;
    value: string;
    onChangeText: (text: string) => void;
    onSave: () => void;
  }) => {
    const { Text, TextInput, View } = jest.requireActual("react-native");
    if (!visible) return null;
    return (
      <View>
        <TextInput testID="edit-field" value={value} onChangeText={onChangeText} />
        <Text testID="edit-save" onPress={onSave}>save</Text>
      </View>
    );
  },
}));
jest.mock("expo-router", () => ({
  Redirect: () => null,
  useRouter: () => mockRouter,
  useLocalSearchParams: () => ({ key: mockKey }),
  useFocusEffect: (effect: () => void | (() => void)) => {
    const React = jest.requireActual("react");
    React.useEffect(() => effect(), [effect]);
  },
}));
jest.mock("@/features/memory/hooks/useMemoryDocuments", () => ({
  useMemoryDocuments: () => ({
    documents: mockDocuments,
    loading: mockLoading,
    error: mockError,
    load: mockLoad,
    instruct: mockInstruct,
    deleteDocument: mockDeleteDocument,
    deleteFact: mockDeleteFact,
    editFact: mockEditFact,
    setFactMuted: mockSetFactMuted,
  }),
}));

const fact = (id: string, text: string) => ({
  id,
  type: "project",
  topic: "area:recall",
  text,
  confidence: 0.9,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-21T00:00:00Z",
});

async function flush() {
  await new Promise<void>((resolve) => setImmediate(resolve));
}

beforeEach(() => {
  jest.clearAllMocks();
  mockKey = "area:recall";
  mockLoading = false;
  mockError = false;
  mockConfirm.mockResolvedValue(true);
  mockDocuments = [
    {
      key: "area:recall",
      group: "areas",
      title: "Recall",
      summary: "Personal AI chat app",
      updated_at: "2026-08-21T00:00:00Z",
      facts: [
        fact("f1", "As of 2026-08-01: User is building Recall with Expo"),
        fact("f2", "Recall uses FastAPI"),
      ],
    },
  ];
});

describe("MemoryDocumentScreen", () => {
  it("offers delete this page and clear all memories in the top-right menu", async () => {
    const ui = await render(<MemoryDocumentScreen />);
    expect(ui.getByText("memory.delete_page")).toBeTruthy();
    await act(async () => {
      fireEvent.press(ui.getByTestId("menu-clear-all"));
    });
    expect(mockClearAll).toHaveBeenCalled();
  });

  it("shows the page: title, last updated, summary and details", async () => {
    const ui = await render(<MemoryDocumentScreen />);
    expect(ui.getByText("Recall")).toBeTruthy();
    expect(ui.getByText("memory.last_updated")).toBeTruthy();
    expect(ui.getByText("Personal AI chat app")).toBeTruthy();
    // The freshness stamp is the server's, not part of the fact.
    expect(ui.getByText("User is building Recall with Expo")).toBeTruthy();
    expect(ui.getByText("Recall uses FastAPI")).toBeTruthy();
  });

  it("deletes the whole page after confirming", async () => {
    mockDeleteDocument.mockResolvedValue({ ok: true });
    const ui = await render(<MemoryDocumentScreen />);
    await fireEvent.press(ui.getByTestId("memory-document-delete"));
    await flush();

    expect(mockConfirm).toHaveBeenCalledWith(expect.objectContaining({ destructive: true }));
    expect(mockDeleteDocument).toHaveBeenCalledWith("area:recall");
    expect(mockRouter.back).toHaveBeenCalled();
    // One destructive haptic once it is gone, as every delete plays.
    expect(mockDestructive).toHaveBeenCalledTimes(1);
  });

  it("keeps the page when delete is cancelled", async () => {
    mockConfirm.mockResolvedValue(false);
    const ui = await render(<MemoryDocumentScreen />);
    await fireEvent.press(ui.getByTestId("memory-document-delete"));
    await flush();
    expect(mockDeleteDocument).not.toHaveBeenCalled();
    expect(mockRouter.back).not.toHaveBeenCalled();
    expect(mockDestructive).not.toHaveBeenCalled();
  });

  it("edits one fact from its menu", async () => {
    mockEditFact.mockResolvedValue({ ok: true });
    const ui = await render(<MemoryDocumentScreen />);
    await fireEvent.press(ui.getByTestId("memory-fact-f2"), { nativeEvent: { pageX: 10, pageY: 20 } });
    await fireEvent.press(ui.getByTestId("menu-edit"));
    await fireEvent.changeText(ui.getByTestId("edit-field"), "Recall uses FastAPI and Neon");
    await fireEvent.press(ui.getByTestId("edit-save"));
    await flush();

    expect(mockEditFact).toHaveBeenCalledWith("f2", "Recall uses FastAPI and Neon");
    expect(ui.queryByTestId("edit-field")).toBeNull();
  });

  it("draws no fact again while its menu opens or the edit sheet is typed in", async () => {
    const facts = Array.from({ length: 150 }, (_, i) => fact(`f${i}`, `Remembered fact ${i}`));
    mockDocuments = [{ ...mockDocuments[0]!, facts }];
    const ui = await render(<MemoryDocumentScreen />);
    mockFactsDrawn.count = 0;
    await fireEvent.press(ui.getByTestId("memory-fact-f3"), { nativeEvent: { pageX: 10, pageY: 20 } });
    expect(mockFactsDrawn.count).toBe(0);
    await fireEvent.press(ui.getByTestId("menu-edit"));
    mockFactsDrawn.count = 0;
    for (const text of ["Remembered", "Remembered fact", "Remembered fact 3!"]) {
      await fireEvent.changeText(ui.getByTestId("edit-field"), text);
    }
    expect(mockFactsDrawn.count).toBe(0);
  });

  it("deletes one fact from its menu", async () => {
    mockDeleteFact.mockResolvedValue({ ok: true });
    const ui = await render(<MemoryDocumentScreen />);
    await fireEvent(ui.getByTestId("memory-fact-f1"), "longPress", { nativeEvent: { pageX: 5, pageY: 5 } });
    await fireEvent.press(ui.getByTestId("menu-delete"));
    await flush();

    expect(mockDeleteFact).toHaveBeenCalledWith("f1");
    // Other facts remain, so the page stays open.
    expect(mockRouter.back).not.toHaveBeenCalled();
    expect(mockDestructive).toHaveBeenCalledTimes(1);
  });

  it("plays no destructive haptic when a fact's delete fails", async () => {
    mockDeleteFact.mockResolvedValue({ ok: false, failure: "failed" });
    const ui = await render(<MemoryDocumentScreen />);
    await fireEvent(ui.getByTestId("memory-fact-f1"), "longPress", { nativeEvent: { pageX: 5, pageY: 5 } });
    await fireEvent.press(ui.getByTestId("menu-delete"));
    await flush();
    expect(mockFeedback.error).toHaveBeenCalled();
    expect(mockDestructive).not.toHaveBeenCalled();
  });

  it("mutes a fact and shows it muted", async () => {
    mockSetFactMuted.mockResolvedValue({ ok: true });
    const ui = await render(<MemoryDocumentScreen />);
    await fireEvent.press(ui.getByTestId("memory-fact-f2"), { nativeEvent: { pageX: 1, pageY: 1 } });
    expect(ui.getByText("memory.mute_fact")).toBeTruthy();
    await fireEvent.press(ui.getByTestId("menu-mute"));
    await flush();
    expect(mockSetFactMuted).toHaveBeenCalledWith("f2", true);

    // The server answers with the muted fact; the page marks it and offers Unmute.
    const [page] = mockDocuments;
    mockDocuments = [
      { ...page, facts: [page.facts[0], { ...page.facts[1], status: "muted" as const }] },
    ];
    await act(async () => {
      ui.rerender(<MemoryDocumentScreen />);
    });
    expect(ui.getByTestId("memory-fact-muted-f2")).toBeTruthy();
    expect(ui.getByText("memory.muted_label")).toBeTruthy();
    await fireEvent.press(ui.getByTestId("memory-fact-f2"), { nativeEvent: { pageX: 1, pageY: 1 } });
    expect(ui.getByText("memory.unmute_fact")).toBeTruthy();
    await fireEvent.press(ui.getByTestId("menu-mute"));
    await flush();
    expect(mockSetFactMuted).toHaveBeenLastCalledWith("f2", false);
  });

  it("says when a mute did not go through", async () => {
    mockSetFactMuted.mockResolvedValue({ ok: false, failure: "failed" });
    const ui = await render(<MemoryDocumentScreen />);
    await fireEvent.press(ui.getByTestId("memory-fact-f1"), { nativeEvent: { pageX: 1, pageY: 1 } });
    await fireEvent.press(ui.getByTestId("menu-mute"));
    await flush();
    expect(mockFeedback.error).toHaveBeenCalledWith("memory.mute_failed");
  });

  it.each([
    ["busy", "memory.busy"],
    // Redis down at the write lock said "Memory is being updated".
    ["unavailable", "common.service_unavailable"],
  ])("says memory is busy, not broken, only when a mute meets another write: %s (CLAR-08)", async (failure, line) => {
    mockSetFactMuted.mockResolvedValue({ ok: false, failure });
    const ui = await render(<MemoryDocumentScreen />);
    await fireEvent.press(ui.getByTestId("memory-fact-f1"), { nativeEvent: { pageX: 1, pageY: 1 } });
    await fireEvent.press(ui.getByTestId("menu-mute"));
    await flush();
    expect(mockFeedback.error).toHaveBeenCalledWith(line);
  });

  it("shows the chat a fact was learned in", async () => {
    mockDocuments[0].facts[0] = {
      ...mockDocuments[0].facts[0],
      source_chat_title: "Building Recall",
    };
    const ui = await render(<MemoryDocumentScreen />);
    expect(ui.getByText("memory.source_chat:Building Recall")).toBeTruthy();
  });

  it("sends edits scoped to this page", async () => {
    mockInstruct.mockResolvedValue({ ok: true, reply: "", applied: 1, dropped: 0 });
    const ui = await render(<MemoryDocumentScreen />);
    await fireEvent.changeText(ui.getByTestId("memory-composer-input"), "It also uses Neon");
    await fireEvent.press(ui.getByTestId("memory-composer-send"));

    expect(mockInstruct).toHaveBeenCalledWith("It also uses Neon", "area:recall");
    expect(mockFeedback.success).toHaveBeenCalledWith("memory.instruct_done");
  });

  it("loads when opened from a link and says when the page is gone", async () => {
    mockKey = "area:unknown";
    const ui = await render(<MemoryDocumentScreen />);
    expect(mockLoad).toHaveBeenCalled();
    await fireEvent.press(ui.getByText("memory.document_gone"));
    expect(mockRouter.back).toHaveBeenCalled();
  });

  it("says the pages failed to load instead of calling the page gone, and retries", async () => {
    mockKey = "area:unknown";
    mockDocuments = [];
    mockError = true;
    const ui = await render(<MemoryDocumentScreen />);
    expect(ui.queryByText("memory.document_gone")).toBeNull();
    mockLoad.mockClear();
    await fireEvent.press(ui.getByText("common.error"));
    expect(mockLoad).toHaveBeenCalledTimes(1);
  });
});
