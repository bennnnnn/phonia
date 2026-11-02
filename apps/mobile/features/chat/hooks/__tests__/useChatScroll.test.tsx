import { act, renderHook } from "@testing-library/react-native";
import type { NativeScrollEvent, NativeSyntheticEvent } from "react-native";

import { useChatScroll } from "@/features/chat/hooks/useChatScroll";
import { MOMENTUM_WAIT_MS } from "@/features/chat/hooks/useReaderDrag";
import { tap } from "@/lib/haptics";

/** The keyboard never moves in these tests. */
const NO_KEYBOARD_STEPS = { subscribe: () => () => {} };

jest.mock("@/lib/haptics", () => ({ tap: jest.fn() }));

/** A FlashList that reports `rows` of content in a `window`, scrolled to `offset`. */
function fakeList(rows: number) {
  const state = { rows, window: 600, offset: 0 };
  const scroller = { scrollToEnd: jest.fn() };
  const list = {
    getAbsoluteLastScrollOffset: () => state.offset,
    getChildContainerDimensions: () => ({ width: 390, height: state.rows }),
    getWindowSize: () => ({ width: 390, height: state.window }),
    getNativeScrollRef: () => scroller,
    scrollToEnd: jest.fn(),
    scrollToOffset: jest.fn(),
  };
  return { state, scroller, list };
}

function scrollEvent(offset: number, content: number, viewport = 600, velocity = 0) {
  return {
    nativeEvent: {
      contentOffset: { x: 0, y: offset },
      contentSize: { width: 390, height: content },
      layoutMeasurement: { width: 390, height: viewport },
      velocity: { x: 0, y: velocity },
    },
  } as NativeSyntheticEvent<NativeScrollEvent>;
}

type Props = { chatId: string | null; messagesLength: number; streamActive: boolean };

async function mountScroll(fake: ReturnType<typeof fakeList>, initial: Props) {
  const hook = await renderHook((props: Props) => useChatScroll({ ...props, windowHeight: 800, keyboardSteps: NO_KEYBOARD_STEPS }), {
    initialProps: initial,
  });
  (hook.result.current.listRef as { current: unknown }).current = fake.list;
  return hook;
}

beforeEach(() => jest.useFakeTimers());
afterEach(() => jest.useRealTimers());

describe("useChatScroll pins to the bottom from layout", () => {
  const props: Props = { chatId: "chat-a", messagesLength: 4, streamActive: true };

  it("follows rows that grew, in the commit that measured them", async () => {
    const fake = fakeList(1000);
    const { result } = await mountScroll(fake, props);
    await act(async () => {
      result.current.listScroll.onLayoutCommit();
    });
    fake.scroller.scrollToEnd.mockClear();

    fake.state.rows = 1060;
    await act(async () => {
      result.current.listScroll.onLayoutCommit();
    });
    expect(fake.scroller.scrollToEnd).toHaveBeenCalledWith({ animated: false });
    // FlashList's own scrollToEnd waits a tick: the native scroller is used instead.
    expect(fake.list.scrollToEnd).not.toHaveBeenCalled();

    // A commit with nothing new does not scroll again.
    fake.scroller.scrollToEnd.mockClear();
    await act(async () => {
      result.current.listScroll.onLayoutCommit();
    });
    expect(fake.scroller.scrollToEnd).not.toHaveBeenCalled();
  });

  it("does not pull the list while the reader drags it, and follows again after", async () => {
    const fake = fakeList(1000);
    const { result } = await mountScroll(fake, props);
    await act(async () => {
      result.current.listScroll.onLayoutCommit();
    });
    fake.scroller.scrollToEnd.mockClear();

    await act(async () => {
      result.current.listScroll.onReaderScrollBegin();
    });
    fake.state.rows = 1100;
    await act(async () => {
      result.current.listScroll.onLayoutCommit();
    });
    expect(fake.scroller.scrollToEnd).not.toHaveBeenCalled();

    fake.state.offset = 500;
    await act(async () => {
      result.current.handleScrollEnd();
    });
    fake.state.rows = 1150;
    await act(async () => {
      result.current.listScroll.onLayoutCommit();
    });
    expect(fake.scroller.scrollToEnd).toHaveBeenCalledTimes(1);
  });

  it("stays put once the reader scrolled away from the bottom", async () => {
    const fake = fakeList(3000);
    const { result } = await mountScroll(fake, props);
    await act(async () => {
      result.current.handleScroll(scrollEvent(200, 3000));
    });
    fake.state.rows = 3200;
    await act(async () => {
      result.current.listScroll.onLayoutCommit();
    });
    expect(fake.scroller.scrollToEnd).not.toHaveBeenCalled();
  });

  it("follows the scroll content too (a settling reply's padding and chrome)", async () => {
    const fake = fakeList(1000);
    const { result } = await mountScroll(fake, props);
    await act(async () => {
      result.current.listScroll.onContentSizeChange(390, 1300);
    });
    fake.scroller.scrollToEnd.mockClear();
    await act(async () => {
      result.current.listScroll.onContentSizeChange(390, 1340);
    });
    expect(fake.scroller.scrollToEnd).toHaveBeenCalledWith({ animated: false });
  });

  it("leaves a thread that fits the screen alone", async () => {
    const fake = fakeList(300);
    const { result } = await mountScroll(fake, props);
    fake.state.rows = 360;
    await act(async () => {
      result.current.listScroll.onLayoutCommit();
    });
    expect(fake.scroller.scrollToEnd).not.toHaveBeenCalled();
  });
});

describe("useChatScroll waits out a flick", () => {
  const props: Props = { chatId: "chat-a", messagesLength: 4, streamActive: true };

  /** A thread at its bottom, its rows measured once. */
  async function atBottom() {
    const fake = fakeList(1000);
    fake.state.offset = 400;
    const hook = await mountScroll(fake, props);
    await act(async () => {
      hook.result.current.listScroll.onLayoutCommit();
    });
    fake.scroller.scrollToEnd.mockClear();
    return { fake, ...hook };
  }

  async function grow(fake: ReturnType<typeof fakeList>, result: { current: ReturnType<typeof useChatScroll> }) {
    fake.state.rows += 50;
    await act(async () => {
      result.current.listScroll.onLayoutCommit();
    });
  }

  it("does not pull the list from the drag's release until its momentum ends", async () => {
    const { fake, result } = await atBottom();
    await act(async () => {
      result.current.listScroll.onReaderScrollBegin();
      result.current.listScroll.onReaderScrollEndDrag(scrollEvent(400, 1000, 600, 1.5));
    });
    // Between the release and the momentum's start the reader still moves the list.
    await grow(fake, result);
    await act(async () => {
      result.current.listScroll.onReaderScrollBegin();
    });
    await grow(fake, result);
    expect(fake.scroller.scrollToEnd).not.toHaveBeenCalled();

    fake.state.offset = fake.state.rows - 600;
    await act(async () => {
      result.current.handleScrollEnd();
    });
    await grow(fake, result);
    expect(fake.scroller.scrollToEnd).toHaveBeenCalledTimes(1);
  });

  it("follows again when no momentum comes after a flick", async () => {
    const { fake, result } = await atBottom();
    await act(async () => {
      result.current.listScroll.onReaderScrollBegin();
      result.current.listScroll.onReaderScrollEndDrag(scrollEvent(400, 1000, 600, 1.5));
    });
    await act(async () => {
      jest.advanceTimersByTime(MOMENTUM_WAIT_MS);
    });
    await grow(fake, result);
    expect(fake.scroller.scrollToEnd).toHaveBeenCalledTimes(1);
  });

  it("ends a drag let go without speed at once", async () => {
    const { fake, result } = await atBottom();
    await act(async () => {
      result.current.listScroll.onReaderScrollBegin();
      result.current.listScroll.onReaderScrollEndDrag(scrollEvent(400, 1000));
    });
    await grow(fake, result);
    expect(fake.scroller.scrollToEnd).toHaveBeenCalledTimes(1);
  });
});

describe("useChatScroll opens a chat at its end", () => {
  const closed: Props = { chatId: null, messagesLength: 0, streamActive: false };

  it("draws an opened chat once a commit finds it at its end", async () => {
    const fake = fakeList(2000);
    const { result, rerender } = await mountScroll(fake, closed);
    await rerender({ chatId: "chat-b", messagesLength: 12, streamActive: false });
    expect(result.current.listScroll.hidden).toBe(true);

    await act(async () => {
      result.current.listScroll.onLayoutCommit();
    });
    expect(fake.scroller.scrollToEnd).toHaveBeenCalledWith({ animated: false });
    expect(result.current.listScroll.hidden).toBe(true);

    fake.state.offset = 1400;
    await act(async () => {
      result.current.listScroll.onLayoutCommit();
    });
    expect(result.current.listScroll.hidden).toBe(false);
  });

  it("draws an opened chat that fits the screen at once", async () => {
    const fake = fakeList(400);
    const { result, rerender } = await mountScroll(fake, closed);
    await rerender({ chatId: "chat-b", messagesLength: 2, streamActive: false });
    expect(result.current.listScroll.hidden).toBe(true);
    await act(async () => {
      result.current.listScroll.onLayoutCommit();
    });
    expect(result.current.listScroll.hidden).toBe(false);
    expect(fake.scroller.scrollToEnd).not.toHaveBeenCalled();
  });

  it("draws it after a short wait if the list never reports its end", async () => {
    const fake = fakeList(2000);
    const { result, rerender } = await mountScroll(fake, closed);
    await rerender({ chatId: "chat-b", messagesLength: 12, streamActive: false });
    expect(result.current.listScroll.hidden).toBe(true);
    await act(async () => {
      jest.advanceTimersByTime(300);
    });
    expect(result.current.listScroll.hidden).toBe(false);
  });

  it("never hides a new chat taking its id under its first message", async () => {
    const fake = fakeList(200);
    const { result, rerender } = await mountScroll(fake, { chatId: null, messagesLength: 1, streamActive: false });
    await rerender({ chatId: "chat-c", messagesLength: 1, streamActive: false });
    expect(result.current.listScroll.hidden).toBe(false);
  });
});

describe("useChatScroll leaves a highlighted search hit to its own scroll", () => {
  it("does not put a chat opened for a hit at its end, nor pull it there as rows grow", async () => {
    const fake = fakeList(2000);
    const { result, rerender } = await mountScroll(fake, { chatId: null, messagesLength: 0, streamActive: false });
    await act(async () => {
      result.current.holdForHighlight(true);
    });
    await rerender({ chatId: "chat-b", messagesLength: 12, streamActive: false });
    expect(result.current.listScroll.hidden).toBe(false);

    await act(async () => {
      result.current.listScroll.onLayoutCommit();
      result.current.listScroll.onListLayout(600);
      result.current.listScroll.onContentSizeChange(390, 2000);
    });
    // The highlight scrolls the list to the hit, well above the end.
    fake.state.offset = 700;
    await act(async () => {
      result.current.handleScroll(scrollEvent(700, 2000));
    });
    fake.state.rows = 2100;
    await act(async () => {
      result.current.listScroll.onLayoutCommit();
      result.current.listScroll.onContentSizeChange(390, 2100);
    });
    expect(fake.scroller.scrollToEnd).not.toHaveBeenCalled();

    // The highlight over, the reader is still at the hit: growth is not followed.
    await act(async () => {
      result.current.holdForHighlight(false);
    });
    fake.state.rows = 2200;
    await act(async () => {
      result.current.listScroll.onLayoutCommit();
      result.current.listScroll.onContentSizeChange(390, 2200);
    });
    expect(fake.scroller.scrollToEnd).not.toHaveBeenCalled();

    // Once the reader is back at the bottom, growth is followed again.
    fake.state.offset = 1600;
    await act(async () => {
      result.current.handleScroll(scrollEvent(1600, 2200));
    });
    fake.state.rows = 2300;
    await act(async () => {
      result.current.listScroll.onLayoutCommit();
    });
    expect(fake.scroller.scrollToEnd).toHaveBeenCalledWith({ animated: false });
  });

  it("draws a chat already opening where it is once its hit is known", async () => {
    const fake = fakeList(2000);
    const { result, rerender } = await mountScroll(fake, { chatId: null, messagesLength: 0, streamActive: false });
    await rerender({ chatId: "chat-b", messagesLength: 12, streamActive: false });
    expect(result.current.listScroll.hidden).toBe(true);

    await act(async () => {
      result.current.holdForHighlight(true);
    });
    expect(result.current.listScroll.hidden).toBe(false);
    await act(async () => {
      result.current.listScroll.onLayoutCommit();
    });
    expect(fake.scroller.scrollToEnd).not.toHaveBeenCalled();
  });
});

describe("useChatScroll keyboard steps", () => {
  it("do not pull the list while the reader drags it (an interactive keyboard dismiss)", async () => {
    const listeners = new Set<(height: number) => void>();
    const keyboardSteps = {
      subscribe: (listener: (height: number) => void) => {
        listeners.add(listener);
        return () => { listeners.delete(listener); };
      },
    };
    const fake = fakeList(1600);
    fake.state.offset = 1000;
    const hook = await renderHook(() => useChatScroll({
      chatId: "chat-a", messagesLength: 8, streamActive: false, windowHeight: 800, keyboardSteps,
    }));
    (hook.result.current.listRef as { current: unknown }).current = fake.list;
    await act(async () => { jest.advanceTimersByTime(400); });
    fake.list.scrollToEnd.mockClear();
    fake.scroller.scrollToEnd.mockClear();

    await act(async () => { hook.result.current.listScroll.onReaderScrollBegin(); });
    await act(async () => {
      for (const height of [300, 250, 200]) {
        listeners.forEach((listener) => listener(height));
        jest.advanceTimersByTime(60);
      }
    });
    expect(fake.list.scrollToEnd).not.toHaveBeenCalled();
    expect(fake.scroller.scrollToEnd).not.toHaveBeenCalled();
  });
});

// Image generation and live talk call it after every picture and voice turn: no haptic
// there. The scroll button's press plays its own (ChatScrollFab).
it("scrolls to the latest message without a haptic of its own", async () => {
  jest.mocked(tap).mockClear();
  const fake = fakeList(2000);
  const { result } = await mountScroll(fake, { chatId: "chat-a", messagesLength: 4, streamActive: false });
  await act(async () => { result.current.scrollToLatest(); });
  expect(fake.list.scrollToEnd).toHaveBeenCalled();
  expect(tap).not.toHaveBeenCalled();
});
