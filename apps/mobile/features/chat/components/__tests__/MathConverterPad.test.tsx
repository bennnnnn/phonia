import { act, fireEvent, render } from "@testing-library/react-native";

import { MathConverterPad } from "@/features/chat/components/MathConverterPad";
import { createStreamCueGate } from "@/features/chat/model/streamFeedback";
import { notifyWarning, selection, tap } from "@/lib/haptics";

jest.mock("@/lib/haptics", () => ({ tap: jest.fn(), selection: jest.fn(), notifyWarning: jest.fn() }));

const hapticCount = () =>
  [tap, selection, notifyWarning].reduce((sum, fn) => sum + jest.mocked(fn).mock.calls.length, 0);

beforeEach(() => jest.clearAllMocks());

it("ticks for a digit key", async () => {
  const view = await render(<MathConverterPad keyHeight={44} onAsk={jest.fn()} onStop={jest.fn()} streaming={false} />);
  await act(async () => { fireEvent.press(view.getByTestId("math-converter-7")); });
  expect(selection).toHaveBeenCalledTimes(1);
});

// Ask sends through the composer's send, which taps (useChatSend); the pad adds nothing.
it("leaves Ask's haptic to the send it starts", async () => {
  const onAsk = jest.fn();
  const view = await render(<MathConverterPad keyHeight={44} onAsk={onAsk} onStop={jest.fn()} streaming={false} />);
  await act(async () => { fireEvent.press(view.getByTestId("math-converter-ask")); });
  expect(onAsk).toHaveBeenCalledTimes(1);
  expect(hapticCount()).toBe(0);
});

it("plays one haptic when Ask stops a streaming reply", async () => {
  // The chat turn's Stop plays the stopped cue, as the composer's Stop button does.
  const cue = createStreamCueGate();
  cue.activity();
  jest.clearAllMocks();
  const view = await render(<MathConverterPad keyHeight={44} onAsk={jest.fn()} onStop={cue.stopped} streaming />);
  await act(async () => { fireEvent.press(view.getByTestId("math-converter-ask")); });
  expect(tap).toHaveBeenCalledTimes(1);
  expect(hapticCount()).toBe(1);
});
