import React from "react";
import { Text } from "react-native";
import { act, render } from "@testing-library/react-native";

import { useChatRegenerate } from "@/features/chat/hooks/useChatRegenerate";

let currentRegenerate: () => Promise<void>;
let currentRegenerating = false;

function Probe({
  token = "tok",
  regenerateResponse,
  beginRegenerateUi,
}: {
  token?: string | null;
  regenerateResponse: jest.Mock;
  beginRegenerateUi?: jest.Mock;
}) {
  const result = useChatRegenerate({ token, regenerateResponse, beginRegenerateUi });
  React.useLayoutEffect(() => {
    currentRegenerate = result.regenerate;
    currentRegenerating = result.regenerating;
  }, [result]);
  return <Text>{result.regenerating ? "busy" : "idle"}</Text>;
}

describe("useChatRegenerate", () => {
  it("shows typing at the tap, then asks for the reply again", async () => {
    const beginRegenerateUi = jest.fn(() => () => true);
    const regenerateResponse = jest.fn(async () => undefined);
    await render(<Probe regenerateResponse={regenerateResponse} beginRegenerateUi={beginRegenerateUi} />);
    await act(async () => { await currentRegenerate(); });
    expect(beginRegenerateUi).toHaveBeenCalledTimes(1);
    expect(regenerateResponse).toHaveBeenCalledWith();
    expect(currentRegenerating).toBe(false);
  });

  it("sends nothing when the start was refused mid-reply", async () => {
    const regenerateResponse = jest.fn();
    await render(<Probe regenerateResponse={regenerateResponse} beginRegenerateUi={jest.fn(() => () => false)} />);
    await act(async () => { await currentRegenerate(); });
    expect(regenerateResponse).not.toHaveBeenCalled();
    expect(currentRegenerating).toBe(false);
  });

  it("does nothing signed out", async () => {
    const regenerateResponse = jest.fn();
    await render(<Probe token={null} regenerateResponse={regenerateResponse} />);
    await act(async () => { await currentRegenerate(); });
    expect(regenerateResponse).not.toHaveBeenCalled();
  });

  it("blocks duplicate regeneration while the first request is pending", async () => {
    let finish!: () => void;
    const regenerateResponse = jest.fn(() => new Promise<void>((resolve) => { finish = resolve; }));
    await render(<Probe regenerateResponse={regenerateResponse} />);
    let first!: Promise<void>;
    await act(async () => { first = currentRegenerate(); });
    expect(currentRegenerating).toBe(true);
    await act(async () => { await currentRegenerate(); });
    expect(regenerateResponse).toHaveBeenCalledTimes(1);
    await act(async () => { finish(); await first; });
    expect(currentRegenerating).toBe(false);
  });
});
