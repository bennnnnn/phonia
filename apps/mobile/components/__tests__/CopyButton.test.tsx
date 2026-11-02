import { act, fireEvent, render } from "@testing-library/react-native";
import * as Clipboard from "expo-clipboard";

import { CopyButton } from "@/components/CopyButton";

const setStringAsync = Clipboard.setStringAsync as jest.Mock;

async function flushCopied() {
  // onCopy awaits Clipboard.setStringAsync; flush that microtask + the state update.
  await act(async () => {
    await Promise.resolve();
  });
}

describe("CopyButton", () => {
  beforeEach(() => {
    setStringAsync.mockClear();
  });

  it("is icon-only and copies on press", async () => {
    const { getByLabelText, queryByText } = await render(<CopyButton text="hello" />);

    expect(queryByText("common.copy")).toBeNull();
    await fireEvent.press(getByLabelText("common.copy"));
    await flushCopied();

    expect(setStringAsync).toHaveBeenCalledWith("hello");
  });

  it("announces Copied after a successful press", async () => {
    const { getByLabelText } = await render(<CopyButton text="hi" />);

    await fireEvent.press(getByLabelText("common.copy"));
    await flushCopied();

    expect(getByLabelText("common.copied")).toBeOnTheScreen();
  });

  it("resets back to Copy after the timeout", async () => {
    jest.useFakeTimers();
    try {
      const { getByLabelText, queryByLabelText } = await render(<CopyButton text="hi" />);

      await fireEvent.press(getByLabelText("common.copy"));
      await flushCopied();
      expect(getByLabelText("common.copied")).toBeOnTheScreen();

      await act(async () => {
        jest.advanceTimersByTime(1500);
      });

      expect(queryByLabelText("common.copied")).toBeNull();
      expect(getByLabelText("common.copy")).toBeOnTheScreen();
    } finally {
      jest.useRealTimers();
    }
  });

  it("does not copy when the text is blank", async () => {
    const { getByLabelText } = await render(<CopyButton text="   " />);

    await fireEvent.press(getByLabelText("common.copy"));
    await flushCopied();

    expect(setStringAsync).not.toHaveBeenCalled();
  });
});
