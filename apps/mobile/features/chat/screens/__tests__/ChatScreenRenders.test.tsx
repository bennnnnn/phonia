import type { SharedValue } from "react-native-reanimated";
import { act, render } from "@testing-library/react-native";

import HomeScreen from "@/features/chat/screens/ChatScreen";
import { closeDrawer, openDrawer } from "@/features/chat/drawer/drawer";

/**
 * The chat screen while the keyboard and the drawer move: how often it
 * renders, and whether the thread follows the keyboard. Every hook the screen
 * calls is a stub except the keyboard inset, the scroll hook, the layout
 * metrics, the body props and the drawer shell, so a render here is the
 * screen reacting to the keyboard or the drawer and nothing else.
 */

type KeyboardFrame = { state: number; height: number };
type Reaction = { previous: unknown; run: () => void };

jest.mock("react-native-reanimated", () => {
  const React = jest.requireActual("react") as typeof import("react");
  const { View } = jest.requireActual("react-native") as typeof import("react-native");
  const keyboard = { state: { value: 0 }, height: { value: 0 } };
  const reactions = new Set<Reaction>();
  const id = <T,>(value: T) => value;
  return {
    __esModule: true,
    default: { View, createAnimatedComponent: id },
    createAnimatedComponent: id,
    runOnJS: id,
    withSpring: id,
    withTiming: id,
    useAnimatedKeyboard: () => keyboard,
    useAnimatedStyle: (factory: () => object) => factory(),
    useSharedValue: <T,>(value: T) => React.useRef({ value }).current,
    useDerivedValue: <T,>(factory: () => T) => {
      const latest = React.useRef(factory);
      latest.current = factory;
      return React.useRef({
        get value() {
          return latest.current();
        },
      }).current;
    },
    // Runs like a mapper: on every keyboard frame, with the previous result.
    useAnimatedReaction: <T,>(prepare: () => T, react: (next: T, previous: T | null) => void) => {
      const latest = React.useRef({ prepare, react });
      latest.current = { prepare, react };
      React.useEffect(() => {
        const entry: Reaction = {
          previous: null,
          run: () => {
            const next = latest.current.prepare();
            latest.current.react(next, entry.previous as T | null);
            entry.previous = next;
          },
        };
        reactions.add(entry);
        return () => {
          reactions.delete(entry);
        };
      }, []);
    },
    mockEmitKeyboard(frame: KeyboardFrame) {
      keyboard.state.value = frame.state;
      keyboard.height.value = frame.height;
      reactions.forEach((reaction) => reaction.run());
    },
  };
});

const mockChatRenders = jest.fn();
const mockBodyProps = jest.fn();
const mockNoop = () => {};
const mockAsyncNoop = async () => {};
let mockMessages: { id: string }[] = [];

const mockChat = {
  editThread: mockNoop,
  streaming: false,
  finalizing: false,
  sendingMessageId: null,
  sendMessage: mockAsyncNoop,
  rejectedSend: null,
  retryRejectedSend: mockNoop,
  restoreRejectedAttachmentDraft: mockNoop,
  beginRegenerateUi: mockNoop,
  cancelRegenerateUi: mockNoop,
  regenerateResponse: mockAsyncNoop,
  stopGeneration: mockNoop,
  connect: mockNoop,
};
const mockRouteLoader = {
  handleFirstReply: mockAsyncNoop,
  chatTitle: null,
  setChatTitle: mockNoop,
  titleGenerating: false,
  pinned: false,
  setPinned: mockNoop,
  archived: false,
  setArchived: mockNoop,
  chatLoading: false,
  hasMoreOlder: false,
  loadingOlder: false,
  loadOlderMessages: mockAsyncNoop,
  highlightedMessageId: null,
  startNewChat: mockNoop,
};
const mockChatActions = {
  showActionBanner: mockNoop,
  menuVisible: false,
  setMenuVisible: mockNoop,
  renameVisible: false,
  renameText: "",
  setRenameText: mockNoop,
  setRenameVisible: mockNoop,
  actionBanner: null,
  dismissActionBanner: mockNoop,
  handleFeedback: mockNoop,
  handleSaveEmailDraft: async () => true,
  confirmRename: mockAsyncNoop,
  shareVisible: false,
  closeShare: mockNoop,
  loadTranscriptMessages: async () => [],
  onShareFromMenu: mockNoop,
  onExportPdfFromMenu: mockNoop,
  onRenameFromMenu: mockNoop,
  onTogglePinFromMenu: mockNoop,
  onToggleArchiveFromMenu: mockNoop,
  onDeleteFromMenu: mockNoop,
};
const mockSend = {
  setInput: mockNoop,
  pendingAttachment: null,
  removePendingAttachment: mockNoop,
  attachPicking: false,
  sendPhase: "idle",
  attachSheetOpen: false,
  setAttachSheetOpen: mockNoop,
  handleSend: mockAsyncNoop,
  sendTappedLine: mockAsyncNoop,
  restoreComposerDraft: mockNoop,
  handlePickAttachment: mockNoop,
  handleAttachmentSheetSelect: mockAsyncNoop,
  handleMathScanCaptured: mockNoop,
  readScan: async () => null,
  handleMathScanSolve: mockNoop,
  mathScannerOpen: false,
  setMathScannerOpen: mockNoop,
};
const mockLiveTalk = {
  open: mockNoop,
  close: mockNoop,
  toggle: mockAsyncNoop,
  toggleMute: mockNoop,
  yieldToComposer: mockNoop,
  visible: false,
  muted: false,
  phase: "idle",
  recording: false,
};
const mockErrorHandlers = {
  chatError: null,
  handleChatError: mockNoop,
  handleStreamBusy: mockNoop,
  dismissChatError: mockNoop,
  handleRejectedSendChange: mockNoop,
};
const mockQuotaNudge = { show: false, usedPct: 0, dismiss: mockNoop, applyTurnUsage: mockNoop };
const mockImageGen = { generating: false, cancel: mockNoop, submitPrompt: mockAsyncNoop, retry: mockNoop };
const mockDictation = {
  voiceInputAvailable: false,
  voiceRecording: false,
  voiceTranscribing: false,
  voiceMeterLevel: { value: 0 } as SharedValue<number>,
  toggleVoiceInput: mockAsyncNoop,
  cancelVoiceInput: mockNoop,
};
const mockDraft = { activeChatId: null, draftChatId: null };
const mockModels = { isPaid: false, autoEnabled: true, modelEnabledSet: new Set<string>(), AUTO_MODEL_ID: "auto" };
const mockComposerState = { selectedModel: "auto" };
const mockMessageList = { headerTitleLabel: null, renderItem: () => null };
const mockRegenerate = { regenerate: mockAsyncNoop, regenerating: false };
const mockAuth = { token: "token", user: null, updateUser: mockAsyncNoop };
const mockRouter = { push: mockNoop, replace: mockNoop, setParams: mockNoop };

jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => 1 }));
jest.mock("expo-router", () => ({
  Redirect: () => null,
  useLocalSearchParams: () => ({}),
  useRouter: () => mockRouter,
}));
jest.mock("@/contexts/AuthContext", () => ({ useAuth: () => mockAuth }));
jest.mock("@/features/chat/drawer/ConversationList", () => ({ ConversationList: () => null }));
jest.mock("@/features/chat/components/ChatScreenBody", () => ({
  ChatScreenBody: (props: unknown) => {
    mockBodyProps(props);
    return null;
  },
}));
jest.mock("@/features/chat/components/ChatScreenMenuSheets", () => ({ ChatScreenMenuSheets: () => null }));
jest.mock("@/features/chat/components/ChatHeader", () => ({ ChatHeader: () => null }));
jest.mock("@/features/chat/components/ChatComposer", () => ({ COMPOSER_HEIGHT: 56 }));
jest.mock("@/features/attachments/components/ComposerAttachmentPreview", () => ({
  composerAttachmentExtra: () => 0,
}));
jest.mock("@/features/speech/components/LiveTalkOverlay", () => ({ LiveTalkOverlay: () => null }));
jest.mock("@/features/chat/hooks/useChat", () => ({
  useChat: () => {
    mockChatRenders();
    return { ...mockChat, messages: mockMessages };
  },
}));
jest.mock("@/features/chat/hooks/useChatActions", () => ({ useChatActions: () => mockChatActions }));
jest.mock("@/features/chat/hooks/useChatComposerState", () => ({ useChatComposerState: () => mockComposerState }));
jest.mock("@/features/chat/hooks/useComposerDictation", () => ({ useComposerDictation: () => mockDictation }));
jest.mock("@/features/chat/hooks/useChatDraftWarmup", () => ({ useChatDraftWarmup: () => {} }));
jest.mock("@/features/chat/hooks/useChatMessageList", () => ({ useChatMessageList: () => mockMessageList }));
jest.mock("@/features/chat/hooks/useChatRegenerate", () => ({ useChatRegenerate: () => mockRegenerate }));
jest.mock("@/features/chat/hooks/useChatRouteLoader", () => ({ useChatRouteLoader: () => mockRouteLoader }));
const mockSendOptions: { beforeSend?: () => Promise<void> }[] = [];
jest.mock("@/features/chat/hooks/useChatSend", () => ({
  useChatSend: (options: { beforeSend?: () => Promise<void> }) => {
    mockSendOptions.push(options);
    return mockSend;
  },
}));
jest.mock("@/features/speech/hooks/useLiveTalk", () => ({ useLiveTalk: () => mockLiveTalk }));
jest.mock("@/features/chat/hooks/useDraftChat", () => ({ useDraftChat: () => mockDraft }));
jest.mock("@/hooks/useModels", () => ({ useModels: () => mockModels }));
jest.mock("@/contexts/NetworkContext", () => ({ useNetwork: () => ({ isOffline: false }) }));
jest.mock("@/features/chat/hooks/useChatScreenError", () => ({
  useChatErrorHandlers: () => mockErrorHandlers,
  useChatErrorRecovery: () => mockNoop,
  useChatStreamLifecycle: () => undefined,
}));
jest.mock("@/features/chat/hooks/useQuotaNudge", () => ({ useQuotaNudge: () => mockQuotaNudge }));
jest.mock("@/features/todos/context/TodosContext", () => ({ useTodosOptional: () => null }));
jest.mock("@/features/chat/hooks/useChatImageGeneration", () => ({ useChatImageGeneration: () => mockImageGen }));

const { mockEmitKeyboard } = jest.requireMock("react-native-reanimated") as {
  mockEmitKeyboard: (frame: KeyboardFrame) => void;
};

const OPENING = 1;
const OPEN = 2;
const CLOSING = 3;
const CLOSED = 4;
const KEYBOARD_HEIGHT = 336;
const FRAMES = 30;

/** Reanimated's iOS estimate of the keyboard curve (REAKeyboardEventObserver), one value per frame. */
function curve(a2: number, b1: number, b2: number, c1: number, c2: number): number[] {
  return Array.from({ length: FRAMES }, (_, frame) => {
    const x = (frame + 1) / FRAMES;
    return 1 - (1 - x) ** a2 - b1 * x * (1 - x) ** b2 - c1 * x ** 2 * (1 - x) ** c2;
  });
}

const openingFrames: KeyboardFrame[] = curve(4.62, 2.44, 9.82, 0.22, 2.09).map((progress) => ({
  state: OPENING,
  height: Math.round(KEYBOARD_HEIGHT * progress),
}));
const closingFrames: KeyboardFrame[] = curve(5.65, 2.74, 8.38, 0.93, 3.29).map((progress) => ({
  state: CLOSING,
  height: Math.round(KEYBOARD_HEIGHT * (1 - progress)),
}));

/** Keyboard frames reach JS 16 ms apart (60 fps); timers are fake, so the scroll hook's waits run on this clock. */
const FRAME_MS = 16;

/** Each step runs in its own act, the way each keyboard frame reaches JS in its own task, then a frame passes. */
async function rendersDuring(steps: (() => void)[]): Promise<number> {
  const before = mockChatRenders.mock.calls.length;
  for (const step of steps) {
    await act(async () => {
      step();
    });
    await act(async () => {
      jest.advanceTimersByTime(FRAME_MS);
    });
  }
  return mockChatRenders.mock.calls.length - before;
}

async function wait(ms: number): Promise<number> {
  const before = mockChatRenders.mock.calls.length;
  await act(async () => {
    jest.advanceTimersByTime(ms);
  });
  return mockChatRenders.mock.calls.length - before;
}

const emitAll = (frames: KeyboardFrame[]) => frames.map((frame) => () => mockEmitKeyboard(frame));
const frames = (state: number, heights: number[]) => heights.map((height) => ({ state, height }));

type BodyProps = {
  layout: {
    keyboardLift: { value: number };
    restingListBottomPad: number;
    restingComposerClearance: number;
    emptyHeight: number;
  };
  list: { listRef: { current: unknown }; onScroll: (event: unknown) => void };
};
const lastBody = () => mockBodyProps.mock.calls.at(-1)?.[0] as BodyProps;
// Tests have no safe area, so the composer rests on the 10 pt minimum pad.
const IDLE_BOTTOM_PAD = 10;
/** The empty state is the one layout value that waits for the keyboard to settle. */
const emptyHeightWith = (resting: number, keyboard: number) =>
  resting - Math.max(0, keyboard - IDLE_BOTTOM_PAD);

/**
 * A thread taller than the screen (2000 pt to scroll), at `offset`, 2000 being
 * its end. Records when it is pinned to the end again.
 */
function attachList(offset = 2000) {
  let start = Date.now();
  const pinnedAt: number[] = [];
  lastBody().list.listRef.current = {
    scrollToEnd: () => pinnedAt.push(Date.now() - start),
    getAbsoluteLastScrollOffset: () => offset,
    getChildContainerDimensions: () => ({ width: 390, height: 2700 }),
    getWindowSize: () => ({ width: 390, height: 700 }),
  };
  return {
    pinnedAt,
    restartClock: () => {
      start = Date.now();
      pinnedAt.length = 0;
    },
  };
}

beforeEach(() => {
  jest.useFakeTimers();
  mockMessages = [];
  // Nothing is mounted yet, so this only puts the shared keyboard back down.
  mockEmitKeyboard({ state: CLOSED, height: 0 });
});

afterEach(() => {
  jest.useRealTimers();
});

describe("ChatScreen renders", () => {
  it("renders once per keyboard show and once per hide, with the settled height", async () => {
    await render(<HomeScreen />);
    const resting = lastBody().layout.emptyHeight;

    const show = await rendersDuring(
      emitAll([...openingFrames, { state: OPEN, height: KEYBOARD_HEIGHT }]),
    );
    expect(lastBody().layout.emptyHeight).toBe(emptyHeightWith(resting, KEYBOARD_HEIGHT));

    const hide = await rendersDuring(emitAll([...closingFrames, { state: CLOSED, height: 0 }]));
    expect(lastBody().layout.emptyHeight).toBe(resting);

    expect({ show, hide }).toEqual({ show: 1, hide: 1 });
  });

  it("moves the list space and the chrome with each keyboard frame while React holds the resting layout", async () => {
    await render(<HomeScreen />);
    const resting = lastBody().layout;

    const midway = openingFrames[FRAMES / 2];
    await rendersDuring(emitAll(openingFrames.slice(0, FRAMES / 2 + 1)));
    expect(lastBody().layout).toBe(resting);
    expect(resting.keyboardLift.value).toBe(midway.height - IDLE_BOTTOM_PAD);

    await rendersDuring(emitAll([...openingFrames.slice(FRAMES / 2 + 1), { state: OPEN, height: KEYBOARD_HEIGHT }]));
    const open = lastBody().layout;
    expect(open.keyboardLift.value).toBe(KEYBOARD_HEIGHT - IDLE_BOTTOM_PAD);
    expect(open.restingListBottomPad).toBe(resting.restingListBottomPad);
    expect(open.restingComposerClearance).toBe(resting.restingComposerClearance);
    expect(open.emptyHeight).toBe(emptyHeightWith(resting.emptyHeight, KEYBOARD_HEIGHT));
  });

  it("does not render when the drawer opens or closes", async () => {
    await render(<HomeScreen />);

    const open = await rendersDuring([() => openDrawer()]);
    const close = await rendersDuring([() => closeDrawer()]);

    expect({ open, close }).toEqual({ open: 0, close: 0 });
  });
});

describe("ChatScreen sends", () => {
  it("bring the newest message into view, even scrolled up with no newer page to load", async () => {
    // Live: a send while scrolled up left the bubble and the reply below the screen.
    await render(<HomeScreen />);
    const beforeSend = mockSendOptions.at(-1)?.beforeSend;
    expect(beforeSend).toEqual(expect.any(Function));
    await act(async () => {
      await beforeSend?.();
    });
  });
});

describe("ChatScreen when the keyboard changes size, turns back or never reports that it settled", () => {
  it("takes a new height while open (emoji keyboard, QuickType bar) with one render", async () => {
    await render(<HomeScreen />);
    const resting = lastBody().layout.emptyHeight;
    await rendersDuring(emitAll([...openingFrames, { state: OPEN, height: KEYBOARD_HEIGHT }]));

    const taller = KEYBOARD_HEIGHT + 44;
    const grow = await rendersDuring(
      emitAll([...frames(OPENING, [350, 366, taller]), { state: OPEN, height: taller }]),
    );
    expect(grow).toBe(1);
    expect(lastBody().layout.emptyHeight).toBe(emptyHeightWith(resting, taller));
  });

  it("does not render for a drag-to-dismiss the user lets go of", async () => {
    await render(<HomeScreen />);
    const resting = lastBody().layout.emptyHeight;
    await rendersDuring(emitAll([...openingFrames, { state: OPEN, height: KEYBOARD_HEIGHT }]));

    const dragged = await rendersDuring(
      emitAll([
        ...frames(CLOSING, [320, 290, 250, 230]),
        ...frames(OPENING, [260, 300, KEYBOARD_HEIGHT]),
        { state: OPEN, height: KEYBOARD_HEIGHT },
      ]),
    );
    expect(dragged).toBe(0);
    expect(lastBody().layout.emptyHeight).toBe(emptyHeightWith(resting, KEYBOARD_HEIGHT));
  });

  it("settles on a keyboard that stops moving even when OPEN or CLOSED never comes", async () => {
    await render(<HomeScreen />);
    const resting = lastBody().layout.emptyHeight;

    // Android's transition count can stick, leaving the state OPENING or CLOSING for good.
    expect(await rendersDuring(emitAll(openingFrames))).toBe(0);
    expect(await wait(100 - FRAME_MS)).toBe(1);
    expect(lastBody().layout.emptyHeight).toBe(emptyHeightWith(resting, KEYBOARD_HEIGHT));

    expect(await rendersDuring(emitAll(closingFrames))).toBe(0);
    expect(await wait(100 - FRAME_MS)).toBe(1);
    expect(lastBody().layout.emptyHeight).toBe(resting);
  });
});

describe("ChatScreen thread while the keyboard moves", () => {
  it("catches up with the keyboard while it opens and while it closes, not only once it stops", async () => {
    await render(<HomeScreen />);
    const list = attachList();

    // The keyboard is up by frame 26 (416 ms) and reports OPEN at frame 30 (480 ms).
    await rendersDuring(emitAll([...openingFrames, { state: OPEN, height: KEYBOARD_HEIGHT }]));
    await wait(500);
    expect(list.pinnedAt.filter((ms) => ms < 416).length).toBeGreaterThanOrEqual(2);
    // The same moments as when every ~48 pt step rendered the screen (measured on main):
    // the 50 ms wait each step restarts runs out where the keyboard slows between steps.
    expect(list.pinnedAt).toEqual([194, 306, 482]);

    // Down by frame 25 (400 ms).
    list.restartClock();
    await rendersDuring(emitAll([...closingFrames, { state: CLOSED, height: 0 }]));
    await wait(500);
    expect(list.pinnedAt).toEqual([178, 274, 434]);
  });

  it("leaves a thread the reader has scrolled up where it is", async () => {
    mockMessages = [{ id: "m1" }, { id: "m2" }];
    await render(<HomeScreen />);
    const { pinnedAt } = attachList(0);
    await act(async () => {
      lastBody().list.onScroll({
        nativeEvent: {
          contentOffset: { x: 0, y: 0 },
          contentSize: { width: 390, height: 2700 },
          layoutMeasurement: { width: 390, height: 700 },
        },
      });
    });

    await rendersDuring(emitAll([...openingFrames, { state: OPEN, height: KEYBOARD_HEIGHT }]));
    await wait(500);
    expect(pinnedAt).toEqual([]);
  });
});
