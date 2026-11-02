import React from "react";
import { act, render } from "@testing-library/react-native";

import { StreamProgressLabel } from "@/features/chat/components/StreamProgressLabel";

const LABELS: Record<string, string> = {
  "chat.status.thinking_seconds": "Thinking… {{seconds}}s",
  "chat.status.checking": "Checking the answer…",
  "chat.status.finding_photo": "Finding a photo…",
};

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { seconds?: number }) =>
      (LABELS[key] ?? key).replace("{{seconds}}", String(options?.seconds ?? "")),
  }),
}));

const NOW = Date.parse("2026-10-21T12:00:00Z");

describe("StreamProgressLabel", () => {
  beforeEach(() => {
    jest.useFakeTimers({ now: NOW });
  });
  afterEach(() => {
    jest.useRealTimers();
  });

  it("shows thinking only after a second, then counts the seconds", async () => {
    const view = await render(<StreamProgressLabel phase="thinking" startedAt={NOW} />);
    expect(view.queryByTestId("stream-progress-thinking")).toBeNull();

    await act(async () => {
      jest.advanceTimersByTime(1000);
    });
    expect(view.getByText("Thinking… 1s")).toBeTruthy();

    await act(async () => {
      jest.advanceTimersByTime(11_000);
    });
    expect(view.getByText("Thinking… 12s")).toBeTruthy();
  });

  it("counts from when the model started thinking, not from when it was told", async () => {
    const view = await render(<StreamProgressLabel phase="thinking" startedAt={NOW - 2500} />);
    expect(view.getByText("Thinking… 2s")).toBeTruthy();
    await act(async () => {
      jest.advanceTimersByTime(500);
    });
    expect(view.getByText("Thinking… 3s")).toBeTruthy();
  });

  it("names the answer check after a second, and a quick one never shows", async () => {
    const view = await render(<StreamProgressLabel phase="checking" startedAt={NOW} />);
    await act(async () => {
      jest.advanceTimersByTime(600);
    });
    expect(view.queryByText("Checking the answer…")).toBeNull();
    await act(async () => {
      jest.advanceTimersByTime(400);
    });
    expect(view.getByText("Checking the answer…")).toBeTruthy();
  });

  it("names any other step at once, with no timer behind it", async () => {
    const timeouts = jest.spyOn(globalThis, "setTimeout");
    const view = await render(<StreamProgressLabel phase="finding_photo" startedAt={NOW} />);
    expect(view.getByText("Finding a photo…")).toBeTruthy();
    expect(timeouts.mock.calls.some(([, delay]) => delay === 1000)).toBe(false);
    timeouts.mockRestore();
  });

  it("shows nothing for a theater phase", async () => {
    const view = await render(<StreamProgressLabel phase="composing" startedAt={NOW - 5000} />);
    expect(view.toJSON()).toBeNull();
  });
});
