/**
 * The status under a working reply opens on its chosen variant: every label drawn is
 * one the rotation meant to show, never the first variant for a frame before it.
 */
import { act, render } from "@testing-library/react-native";
import { Text } from "react-native";
import type { TFunction } from "i18next";

import { useRotatingStreamStatus } from "@/lib/streamStatusLabel";

const COPY: Record<string, string> = {
  "chat.status.reading_files": "Reading your file…",
  "chat.status.reading_files_1": "Going through the attachment…",
  "chat.status.reading_files_2": "Scanning your document…",
  "chat.status.searching": "Searching the web…",
  "chat.status.searching_1": "Checking sources…",
};
const t = ((key: string) => COPY[key] ?? key) as unknown as TFunction;

let drawn: (string | null)[] = [];
function Status({ phase }: { phase: string }) {
  const label = useRotatingStreamStatus(phase, true, t);
  drawn.push(label);
  return <Text>{label}</Text>;
}

beforeEach(() => {
  drawn = [];
  jest.useFakeTimers();
  jest.spyOn(Math, "random").mockReturnValue(0.9);
});
afterEach(() => {
  jest.useRealTimers();
  jest.restoreAllMocks();
});

it("draws the chosen opening variant from the first frame", async () => {
  await render(<Status phase="reading_files" />);
  expect(new Set(drawn)).toEqual(new Set(["Scanning your document…"]));
});

it("opens a new phase on its own chosen variant, then rotates", async () => {
  const ui = await render(<Status phase="reading_files" />);
  drawn = [];
  await ui.rerender(<Status phase="searching" />);
  expect(new Set(drawn)).toEqual(new Set(["Checking sources…"]));
  await act(async () => {
    jest.advanceTimersByTime(3200);
  });
  expect(drawn.at(-1)).toBe("Searching the web…");
});
