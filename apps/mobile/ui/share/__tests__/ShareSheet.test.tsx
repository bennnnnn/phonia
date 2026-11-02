import { act, fireEvent, render } from "@testing-library/react-native";

import { notifySuccess, tap } from "@/lib/haptics";

import { ShareSheet } from "../ShareSheet";

const mockPresent = jest.fn();
const mockCopy = jest.fn();
jest.mock("@/lib/share", () => ({ presentShareSheet: (...args: unknown[]) => mockPresent(...args) }));
jest.mock("expo-clipboard", () => ({ setStringAsync: (...args: unknown[]) => mockCopy(...args) }));
jest.mock("@/lib/haptics", () => ({ tap: jest.fn(), notifySuccess: jest.fn() }));

const hidden = { includeHiddenElements: true };
const labels = {
  share: "Share",
  copy: "Copy",
  copied: "Copied",
  pdf: "PDF",
  copyText: "Copy text",
  failed: { share: "Could not share", copy: "Could not copy", pdf: "Could not make the PDF" },
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

async function open(props: Partial<Parameters<typeof ShareSheet>[0]> = {}) {
  const load = jest.fn(async () => "# Trip\n\nYou: hi");
  const onExportPdf = jest.fn(async () => undefined);
  const onClose = jest.fn();
  const view = await render(
    <ShareSheet
      visible
      onClose={onClose}
      heading="Share chat"
      note="Shares a copy of this chat as it is now."
      preview={{ title: "Trip", meta: "Recall · Sep 26, 2026" }}
      load={load}
      shareTitle="Trip"
      onExportPdf={onExportPdf}
      labels={labels}
      {...props}
    />,
  );
  return { view, load, onExportPdf, onClose };
}

beforeEach(() => {
  jest.clearAllMocks();
  mockPresent.mockResolvedValue(undefined);
  mockCopy.mockResolvedValue(true);
});

it("shows the preview and opens the OS share menu once the sheet is up", async () => {
  const { view, load } = await open();
  expect(view.getByText("Share chat", hidden)).toBeTruthy();
  expect(view.getByText("Recall · Sep 26, 2026", hidden)).toBeTruthy();
  expect(mockPresent).not.toHaveBeenCalled();
  await act(async () => {
    fireEvent(view.getByTestId("app-sheet-modal", hidden), "show");
  });
  expect(mockPresent).toHaveBeenCalledTimes(1);
  expect(mockPresent).toHaveBeenCalledWith({ message: "# Trip\n\nYou: hi", title: "Trip" });
  expect(load).toHaveBeenCalledTimes(1);
});

it("copies the text once and shows a check", async () => {
  const { view, load } = await open();
  await fireEvent.press(view.getByTestId("share-sheet-copy", hidden));
  expect(mockCopy).toHaveBeenCalledWith("# Trip\n\nYou: hi");
  expect(view.getByTestId("share-sheet-copy", hidden).props.accessibilityLabel).toBe("Copied");
  await fireEvent.press(view.getByTestId("share-sheet-card-copy", hidden));
  expect(mockCopy).toHaveBeenCalledTimes(2);
  expect(load).toHaveBeenCalledTimes(1);
});

it.each(["share-sheet-copy", "share-sheet-card-copy"])("%s plays one success haptic, as every copy does", async (testID) => {
  const { view } = await open();
  await fireEvent.press(view.getByTestId(testID, hidden));
  expect(mockCopy).toHaveBeenCalledTimes(1);
  expect(notifySuccess).toHaveBeenCalledTimes(1);
  expect(tap).not.toHaveBeenCalled();
});

it("taps once for Share and PDF", async () => {
  const { view } = await open();
  await fireEvent.press(view.getByTestId("share-sheet-share", hidden));
  await fireEvent.press(view.getByTestId("share-sheet-pdf", hidden));
  expect(tap).toHaveBeenCalledTimes(2);
  expect(notifySuccess).not.toHaveBeenCalled();
});

it("makes a PDF and says so inline when it fails", async () => {
  const onExportPdf = jest.fn().mockRejectedValueOnce(new Error("print failed")).mockResolvedValueOnce(undefined);
  const { view } = await open({ onExportPdf });
  await fireEvent.press(view.getByTestId("share-sheet-pdf", hidden));
  expect(view.getByTestId("share-sheet-failed", hidden)).toHaveTextContent("Could not make the PDF");
  await fireEvent.press(view.getByTestId("share-sheet-pdf", hidden));
  expect(onExportPdf).toHaveBeenCalledTimes(2);
  expect(view.queryByTestId("share-sheet-failed", hidden)).toBeNull();
});

it("says a failure in its own words when the caller names them", async () => {
  const onExportPdf = jest.fn().mockRejectedValueOnce(new Error("empty"));
  const { view } = await open({
    onExportPdf,
    failureText: (error) => (error instanceof Error && error.message === "empty" ? "Nothing to print yet" : null),
  });
  await act(async () => fireEvent.press(view.getByText("PDF", hidden)));
  expect(view.getByTestId("share-sheet-failed", hidden)).toHaveTextContent("Nothing to print yet");
});

it("treats a cancelled OS menu as no failure", async () => {
  mockPresent.mockRejectedValueOnce(new Error("User did not share"));
  const { view } = await open();
  await fireEvent.press(view.getByTestId("share-sheet-share", hidden));
  expect(view.queryByTestId("share-sheet-failed", hidden)).toBeNull();
});

it("retries a failed load on the next action", async () => {
  const load = jest.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce("text");
  const { view } = await open({ load });
  expect(view.getByTestId("share-sheet-failed", hidden)).toHaveTextContent("Could not share");
  await fireEvent.press(view.getByTestId("share-sheet-copy", hidden));
  expect(mockCopy).toHaveBeenCalledWith("text");
  expect(load).toHaveBeenCalledTimes(2);
});

it("does not share text that arrives after the sheet closed", async () => {
  const text = deferred<string>();
  const props = { load: jest.fn(() => text.promise) };
  const { view, onClose } = await open(props);
  await act(async () => {
    fireEvent(view.getByTestId("app-sheet-modal", hidden), "show");
  });
  await view.rerender(
    <ShareSheet
      visible={false}
      onClose={onClose}
      heading="Share chat"
      preview={{ title: "Trip" }}
      load={props.load}
      labels={labels}
    />,
  );
  await act(async () => {
    text.resolve("private");
  });
  expect(mockPresent).not.toHaveBeenCalled();
});
