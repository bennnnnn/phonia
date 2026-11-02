import { act, fireEvent, render } from "@testing-library/react-native";
import {
  Keyboard,
  Platform,
  StyleSheet,
  Text,
  type EmitterSubscription,
  type KeyboardEvent,
} from "react-native";

import { Layer } from "@/lib/layer";
import { Space } from "@/lib/space";

import { floatingSheetBottomMargin, Sheet } from "../Sheet";

/** A stand-in keyboard subscription: the sheet only ever removes it. */
function fakeSubscription(): EmitterSubscription {
  return { remove: jest.fn() } as Partial<EmitterSubscription> as EmitterSubscription;
}

jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 34, left: 0, right: 0 }),
}));

jest.mock("@/lib/reduceMotion", () => ({
  useReduceMotion: () => false,
}));

describe("Sheet", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("renders its children when visible", async () => {
    const { getByText } = await render(
      <Sheet visible onClose={jest.fn()}>
        <Text>sheet body</Text>
      </Sheet>,
    );

    expect(getByText("sheet body")).toBeOnTheScreen();
  });

  it("calls onClose when the scrim is pressed (backdropDismiss default true)", async () => {
    const onClose = jest.fn();
    const { getByTestId } = await render(
      <Sheet visible onClose={onClose}>
        <Text>body</Text>
      </Sheet>,
    );

    await fireEvent.press(getByTestId("app-sheet-backdrop"));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not dismiss on scrim press when backdropDismiss is false", async () => {
    const onClose = jest.fn();
    const { getByTestId } = await render(
      <Sheet visible onClose={onClose} backdropDismiss={false}>
        <Text>body</Text>
      </Sheet>,
    );

    await fireEvent.press(
      getByTestId("app-sheet-backdrop", { includeHiddenElements: true }),
    );

    expect(onClose).not.toHaveBeenCalled();
  });

  it("renders the grabber handle for the bottom variant by default", async () => {
    const { queryByTestId } = await render(
      <Sheet visible onClose={jest.fn()}>
        <Text>body</Text>
      </Sheet>,
    );

    expect(queryByTestId("app-sheet-handle")).not.toBeNull();
  });

  it("omits the handle for the center variant", async () => {
    const { queryByTestId } = await render(
      <Sheet visible onClose={jest.fn()} variant="center">
        <Text>body</Text>
      </Sheet>,
    );

    expect(queryByTestId("app-sheet-handle")).toBeNull();
  });

  it("omits the handle when withHandle is false", async () => {
    const { queryByTestId } = await render(
      <Sheet visible onClose={jest.fn()} withHandle={false}>
        <Text>body</Text>
      </Sheet>,
    );

    expect(queryByTestId("app-sheet-handle")).toBeNull();
  });

  it("ends a floating sheet above the composer instead of under it", async () => {
    const composerClearance = 96;
    const safeOnly = floatingSheetBottomMargin({ safeAreaBottom: 34 });
    expect(safeOnly).toBeLessThan(composerClearance);

    const margin = floatingSheetBottomMargin({
      safeAreaBottom: 34,
      bottomOffset: composerClearance,
    });
    expect(margin).toBeGreaterThanOrEqual(composerClearance);
    expect(margin).toBe(composerClearance + Space.sm);

    const { getByTestId, getByText } = await render(
      <Sheet visible embedded floating bottomOffset={composerClearance} onClose={jest.fn()}>
        <Text>File</Text>
      </Sheet>,
    );

    expect(getByText("File")).toBeOnTheScreen();
    const panel = StyleSheet.flatten(getByTestId("app-sheet-dialog").props.style);
    expect(panel.marginBottom).toBeGreaterThanOrEqual(composerClearance);
    const host = StyleSheet.flatten(getByTestId("app-sheet-embedded").props.style);
    expect(host.zIndex).toBe(Layer.sheet);
  });

  it("renders floating sheets with a handle still visible", async () => {
    const { getByText, queryByTestId } = await render(
      <Sheet visible onClose={jest.fn()} floating>
        <Text>floating body</Text>
      </Sheet>,
    );

    expect(getByText("floating body")).toBeOnTheScreen();
    expect(queryByTestId("app-sheet-handle")).not.toBeNull();
  });

  it("BUG FIX regression: lifts the bottom sheet above the keyboard (Android Modal)", async () => {
    const showEvent = Platform.OS === "ios" ? "keyboardWillShow" : "keyboardDidShow";
    let showHandler: ((e: KeyboardEvent) => void) | undefined;
    jest.spyOn(Keyboard, "addListener").mockImplementation((event, handler) => {
      if (event === showEvent) {
        showHandler = handler as (e: KeyboardEvent) => void;
      }
      return fakeSubscription();
    });

    const { getByTestId } = await render(
      <Sheet visible onClose={jest.fn()} keyboardAvoiding>
        <Text>new list</Text>
      </Sheet>,
    );

    expect(getByTestId("app-sheet-keyboard-host")).toHaveStyle({ paddingBottom: 0 });

    await act(async () => {
      showHandler?.({
        endCoordinates: { height: 320, screenX: 0, screenY: 0, width: 0 },
      } as KeyboardEvent);
    });

    expect(getByTestId("app-sheet-keyboard-host")).toHaveStyle({ paddingBottom: 320 });
  });

  it("BUG FIX regression: clamps tall keyboard sheets so content can scroll", async () => {
    const showEvent = Platform.OS === "ios" ? "keyboardWillShow" : "keyboardDidShow";
    let showHandler: ((e: KeyboardEvent) => void) | undefined;
    jest.spyOn(Keyboard, "addListener").mockImplementation((event, handler) => {
      if (event === showEvent) {
        showHandler = handler as (e: KeyboardEvent) => void;
      }
      return fakeSubscription();
    });

    const { getByText, getByTestId } = await render(
      <Sheet visible onClose={jest.fn()} keyboardAvoiding>
        <Text>reminder body</Text>
      </Sheet>,
    );

    await act(async () => {
      showHandler?.({
        endCoordinates: { height: 400, screenX: 0, screenY: 0, width: 0 },
      } as KeyboardEvent);
    });

    expect(getByText("reminder body")).toBeOnTheScreen();
    // Host still lifts by the keyboard height (reminder / calendar sheet).
    expect(getByTestId("app-sheet-keyboard-host")).toHaveStyle({ paddingBottom: 400 });
  });

  it("exposes dialog semantics and a localized scrim label", async () => {
    const { getByTestId, getByLabelText } = await render(
      <Sheet visible onClose={jest.fn()}>
        <Text>body</Text>
      </Sheet>,
    );

    expect(getByTestId("app-sheet-dialog").props.accessibilityRole).toBe("dialog");
    expect(getByTestId("app-sheet-dialog").props.accessibilityViewIsModal).toBe(true);
    expect(getByLabelText("common.close")).toBeTruthy();
  });

  it("always wires hardware back; no-ops when backdropDismiss is false", async () => {
    const dismissed = jest.fn();
    const blocked = jest.fn();
    const open = await render(
      <Sheet visible onClose={dismissed}>
        <Text>open</Text>
      </Sheet>,
    );
    await fireEvent(open.getByTestId("app-sheet-modal"), "requestClose");
    expect(dismissed).toHaveBeenCalledTimes(1);
    await open.unmount();

    const locked = await render(
      <Sheet visible onClose={blocked} backdropDismiss={false}>
        <Text>locked</Text>
      </Sheet>,
    );
    await fireEvent(locked.getByTestId("app-sheet-modal"), "requestClose");
    expect(blocked).not.toHaveBeenCalled();
  });

  it("closes on VoiceOver's escape scrub only when it may be dismissed", async () => {
    const dismissed = jest.fn();
    const blocked = jest.fn();
    // A centred sheet is modal over its own scrim, so escape is the reader's only way out.
    const open = await render(
      <Sheet visible onClose={dismissed} variant="center">
        <Text>open</Text>
      </Sheet>,
    );
    await fireEvent(open.getByTestId("app-sheet-dialog"), "accessibilityEscape");
    expect(dismissed).toHaveBeenCalledTimes(1);
    await open.unmount();

    const locked = await render(
      <Sheet visible onClose={blocked} backdropDismiss={false}>
        <Text>locked</Text>
      </Sheet>,
    );
    expect(locked.getByTestId("app-sheet-dialog").props.onAccessibilityEscape).toBeUndefined();
    expect(blocked).not.toHaveBeenCalled();
  });
});
