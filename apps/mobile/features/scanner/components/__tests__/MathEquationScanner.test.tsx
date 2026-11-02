import React from "react";
import { Dimensions, StyleSheet } from "react-native";
import { deleteAsync } from "expo-file-system/legacy";

import { pickFromPhotoLibrary, pickImageDocument } from "@/features/attachments/model/attachments";
import { act, fireEvent, render, within } from "@testing-library/react-native";

import { MathEquationScanner } from "@/features/scanner/components/MathEquationScanner";
import { cropScanImage, measureScanImage } from "@/features/scanner/model/scanImage";
import { selection } from "@/lib/haptics";
import { playScannerSwitchCue } from "@/features/scanner/model/switchCue";
import { AA, compositeOver, contrastRatio } from "@/lib/__tests__/support/contrast";

const mockTakePictureAsync = jest.fn(async (): Promise<{ uri: string } | null> => ({
  uri: "file:///shot.jpg",
}));
/** Decoded sizes by file, as the manipulator reports them. */
const MOCK_SIZES: Record<string, { width: number; height: number }> = {
  "file:///shot.jpg": { width: 800, height: 1200 },
  "file:///landscape.png": { width: 1200, height: 700 },
};
const mockPermission = { granted: true, canAskAgain: true };

jest.mock("expo-image-picker", () => ({
  useCameraPermissions: () => [mockPermission, jest.fn()],
}));

jest.mock("@/features/scanner/components/LiveMathScannerCamera", () => {
  const ReactNative = jest.requireActual<typeof import("react")>("react");
  const { View } = jest.requireActual<typeof import("react-native")>("react-native");
  const LiveMathScannerCamera = ReactNative.forwardRef(
    (
      props: {
        onReady?: () => void;
        onUnavailable?: () => void;
        onDetectionChange?: (detection: {
          hasText: boolean;
          stable: boolean;
          text: string;
        }) => void;
      },
      ref: React.Ref<unknown>,
    ) => {
      ReactNative.useImperativeHandle(ref, () => ({ takePictureAsync: mockTakePictureAsync }));
      ReactNative.useEffect(() => {
        let cancelled = false;
        queueMicrotask(() => {
          if (!cancelled) props.onReady?.();
        });
        return () => {
          cancelled = true;
        };
      }, [props.onReady]);
      // The camera's callbacks ride on the host view, where the tests call them.
      const callbacks = { onDetectionChange: props.onDetectionChange, onUnavailable: props.onUnavailable };
      return ReactNative.createElement(View, { testID: "mock-live-scanner-camera", ...callbacks });
    },
  );
  LiveMathScannerCamera.displayName = "LiveMathScannerCamera";
  return { LiveMathScannerCamera };
});

jest.mock("expo-image-manipulator", () => ({
  ImageManipulator: {},
  SaveFormat: { JPEG: "jpeg" },
}));
jest.mock("expo-file-system/legacy", () => ({ deleteAsync: jest.fn(async () => undefined) }));
jest.mock("@/features/scanner/model/scanImage", () => ({
  ...jest.requireActual("@/features/scanner/model/scanImage"),
  cropScanImage: jest.fn(),
  measureScanImage: jest.fn(),
}));

function mockScanImages() {
  jest.mocked(measureScanImage).mockImplementation(async (uri) => MOCK_SIZES[uri]);
  jest.mocked(cropScanImage).mockImplementation(async (uri, cropFor) => {
    const crop = cropFor(MOCK_SIZES[uri]);
    return { uri: "file:///cropped.jpg", width: crop.width, height: crop.height };
  });
}

function deletedFiles(): string[] {
  return jest.mocked(deleteAsync).mock.calls.map(([uri]) => uri);
}

jest.mock("expo-linear-gradient", () => {
  return { LinearGradient: "LinearGradient" };
});

jest.mock("@/features/attachments/model/attachments", () => ({
  pickFromPhotoLibrary: jest.fn(async () => null),
  pickImageDocument: jest.fn(async () => null),
  NativePickerBusyError: class extends Error {},
  NativePickerTimeoutError: class extends Error {},
  PhotoLibraryPermissionError: class extends Error {
    needsSettings = false;
  },
}));

jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 47, bottom: 34, left: 0, right: 0 }),
}));
const mockTheme = { dark: false };
jest.mock("@/lib/theme", () => {
  const actual = jest.requireActual("@/lib/theme");
  return { ...actual, useTheme: () => (mockTheme.dark ? actual.darkTheme : actual.lightTheme) };
});
jest.mock("@/lib/haptics", () => ({
  impactMedium: jest.fn(),
  selection: jest.fn(),
  tap: jest.fn(),
}));
jest.mock("@/features/scanner/model/switchCue", () => ({
  playScannerSwitchCue: jest.fn(async () => undefined),
  stopScannerSwitchCue: jest.fn(),
}));
jest.mock("@/lib/scheduleIdle", () => ({
  scheduleIdlePromise: () => Promise.resolve(),
}));
jest.mock("@/lib/reduceMotion", () => ({
  useReduceMotion: () => false,
}));

describe("MathEquationScanner", () => {
  beforeEach(() => {
    mockTakePictureAsync.mockClear();
    jest.mocked(cropScanImage).mockClear();
    jest.mocked(deleteAsync).mockClear();
    mockScanImages();
    mockPermission.granted = true;
    mockPermission.canAskAgain = true;
  });

  it("keeps the Modal mounted when visible goes false", async () => {
    const view = await render(
      <MathEquationScanner visible onClose={jest.fn()} onCaptured={jest.fn()} />,
    );
    expect(view.getByTestId("math-scanner-modal")).toBeTruthy();
    view.rerender(
      <MathEquationScanner visible={false} onClose={jest.fn()} onCaptured={jest.fn()} />,
    );
    expect(
      view.getByTestId("math-scanner-modal", { includeHiddenElements: true }),
    ).toBeTruthy();
  });

  it("keeps the shutter disc while the photo library is opening", async () => {
    let release: (picked: null) => void = () => undefined;
    jest.mocked(pickFromPhotoLibrary).mockImplementation(
      () =>
        new Promise((resolve) => {
          release = resolve;
        }),
    );
    const view = await render(
      <MathEquationScanner visible onClose={jest.fn()} onCaptured={jest.fn()} />,
    );
    await act(async () => {
      fireEvent.press(view.getByTestId("math-scanner-photos"));
    });
    expect(view.getByTestId("math-scanner-shutter-disc")).toBeTruthy();
    await act(async () => {
      release(null);
    });
    jest.mocked(pickFromPhotoLibrary).mockResolvedValue(null);
  });

  it("shows a live crop frame with the selector and torch beside the shutter", async () => {
    const { getByTestId, getByLabelText, queryByLabelText, queryByTestId } = await render(
      <MathEquationScanner visible onClose={jest.fn()} onCaptured={jest.fn()} />,
    );
    expect(getByTestId("math-scanner-photos")).toBeTruthy();
    expect(getByLabelText("chat.math_scan_capture_a11y")).toBeTruthy();
    expect(queryByLabelText("chat.math_scan_reset_frame")).toBeNull();
    expect(getByTestId("scanner-subject-switcher")).toBeTruthy();
    expect(getByLabelText("chat.math_scan_frame_a11y")).toBeTruthy();
    expect(queryByTestId("math-scanner-shimmer")).toBeNull();
    expect(getByTestId("math-scanner-torch").parent?.parent).toBe(
      getByTestId("math-scanner-shutter").parent,
    );
    expect(getByTestId("math-scanner-camera")).toBeTruthy();
    expect(getByTestId("mock-live-scanner-camera")).toBeTruthy();
    expect(getByTestId("math-scanner-frame-idle")).toBeTruthy();
    expect(getByTestId("scanner-subject-guide-math")).toBeTruthy();
  });

  it("marks the live frame ready after stable on-device OCR", async () => {
    const view = await render(
      <MathEquationScanner visible onClose={jest.fn()} onCaptured={jest.fn()} />,
    );
    const nativeCamera = view.getByTestId("mock-live-scanner-camera");
    await act(async () => {
      nativeCamera.props.onDetectionChange?.({
        hasText: true,
        stable: true,
        text: "2x + 3 = 7",
      });
    });
    expect(view.getByTestId("math-scanner-frame-ready")).toBeTruthy();
    expect(selection).toHaveBeenCalled();
  });

  it("says the live camera needs a newer build when the native camera is missing", async () => {
    const view = await render(
      <MathEquationScanner visible onClose={jest.fn()} onCaptured={jest.fn()} />,
    );
    await act(async () => {
      view.getByTestId("mock-live-scanner-camera").props.onUnavailable?.();
    });
    expect(view.getByText("chat.math_scan_camera_needs_build")).toBeTruthy();
    expect(view.queryByText("chat.math_scan_camera_unavailable")).toBeNull();
    expect(view.getByTestId("math-scanner-photos")).toBeTruthy();
  });

  // Danger ink on the 65% scrim over a white page measured 1.45:1 light, 2.52 dark.
  it.each([
    ["light", false],
    ["dark", true],
  ] as const)("keeps a camera error readable over a white page in %s mode", async (_scheme, dark) => {
    mockTheme.dark = dark;
    try {
      const view = await render(
        <MathEquationScanner visible onClose={jest.fn()} onCaptured={jest.fn()} />,
      );
      await act(async () => {
        view.getByTestId("mock-live-scanner-camera").props.onUnavailable?.();
      });
      const plate = view.getByTestId("math-scanner-error");
      const ink = String(StyleSheet.flatten(within(plate).getByText("chat.math_scan_camera_needs_build").props.style).color);
      const scrim = String(StyleSheet.flatten(plate.props.style).backgroundColor);
      expect(contrastRatio(ink, compositeOver(scrim, "#FFFFFF"))).toBeGreaterThanOrEqual(AA);
      // Without red ink, an icon says it is an error.
      expect(within(plate).getByTestId("math-scanner-error-icon").props).toMatchObject({
        name: "alert-circle",
        color: ink,
      });
    } finally {
      mockTheme.dark = false;
    }
  });

  it("switches to physics with one directional sound and haptic cue", async () => {
    const { getByTestId } = await render(
      <MathEquationScanner visible onClose={jest.fn()} onCaptured={jest.fn()} />,
    );
    await act(async () => {
      fireEvent.press(getByTestId("scanner-subject-physics"));
    });
    expect(selection).toHaveBeenCalled();
    expect(playScannerSwitchCue).toHaveBeenCalledWith(1);
    expect(getByTestId("scanner-subject-guide-physics")).toBeTruthy();
  });

  it("reads a chemistry photo through the chemistry reader, not as math", async () => {
    const onReadScan = jest.fn(async () => null);
    const { getByTestId, getByLabelText } = await render(
      <MathEquationScanner
        visible
        onClose={jest.fn()}
        onCaptured={jest.fn()}
        onReadScan={onReadScan}
        onSolveReading={jest.fn()}
      />,
    );
    await act(async () => {
      fireEvent.press(getByTestId("scanner-subject-chemistry"));
    });
    await act(async () => {
      fireEvent.press(getByLabelText("chat.math_scan_capture_a11y"));
    });
    expect(onReadScan).toHaveBeenCalledTimes(1);
    expect(onReadScan).toHaveBeenCalledWith(
      expect.objectContaining({ localUri: "file:///cropped.jpg" }),
      "chemistry",
      expect.anything(),
    );
  });

  it("shows the biology guide when biology is selected", async () => {
    const { getByTestId } = await render(
      <MathEquationScanner visible onClose={jest.fn()} onCaptured={jest.fn()} />,
    );
    await act(async () => {
      fireEvent.press(getByTestId("scanner-subject-biology"));
    });
    expect(getByTestId("scanner-subject-guide-biology")).toBeTruthy();
  });

  it("does not take hidden camera photos while the scanner is idle", async () => {
    jest.useFakeTimers();
    const view = await render(
      <MathEquationScanner visible onClose={jest.fn()} onCaptured={jest.fn()} />,
    );
    try {
      await act(async () => {
        jest.advanceTimersByTime(15_000);
        await Promise.resolve();
      });
      expect(mockTakePictureAsync).not.toHaveBeenCalled();
    } finally {
      view.unmount();
      jest.useRealTimers();
    }
  });

  it("labels the permission CTA when the camera is denied", async () => {
    mockPermission.granted = false;
    const { getByTestId, getByLabelText } = await render(
      <MathEquationScanner visible onClose={jest.fn()} onCaptured={jest.fn()} />,
    );
    expect(getByTestId("math-scanner-permission")).toBeTruthy();
    expect(getByLabelText("chat.math_scan_allow_camera")).toBeTruthy();
  });

  it("without the camera, reads an image from Photos or from Files", async () => {
    jest.mocked(pickFromPhotoLibrary).mockClear();
    jest.mocked(pickImageDocument).mockClear();
    mockPermission.granted = false;
    const view = await render(
      <MathEquationScanner visible onClose={jest.fn()} onCaptured={jest.fn()} />,
    );
    await act(async () => {
      fireEvent.press(view.getByTestId("math-scanner-permission-photos"));
    });
    expect(pickFromPhotoLibrary).toHaveBeenCalledTimes(1);
    expect(pickImageDocument).not.toHaveBeenCalled();
    await act(async () => {
      fireEvent.press(view.getByTestId("math-scanner-permission-files"));
    });
    expect(pickImageDocument).toHaveBeenCalledTimes(1);
  });

  it("opens Photos on a tap and Files on a long press of the library button", async () => {
    jest.mocked(pickFromPhotoLibrary).mockClear();
    jest.mocked(pickImageDocument).mockClear();
    const view = await render(
      <MathEquationScanner visible onClose={jest.fn()} onCaptured={jest.fn()} />,
    );
    await act(async () => {
      fireEvent.press(view.getByTestId("math-scanner-photos"));
    });
    expect(pickFromPhotoLibrary).toHaveBeenCalledTimes(1);
    await act(async () => {
      fireEvent(view.getByTestId("math-scanner-photos"), "longPress");
    });
    expect(pickImageDocument).toHaveBeenCalledTimes(1);
  });

  it("crops the live camera frame immediately instead of requiring a second Solve tap", async () => {
    const onCaptured = jest.fn();
    const { getByTestId, getByLabelText, queryByTestId } = await render(
      <MathEquationScanner visible onClose={jest.fn()} onCaptured={onCaptured} />,
    );
    await act(async () => {
      fireEvent.press(getByLabelText("chat.math_scan_capture_a11y"));
    });
    expect(mockTakePictureAsync).toHaveBeenCalledTimes(1);
    expect(cropScanImage).toHaveBeenCalledWith("file:///shot.jpg", expect.any(Function));
    expect(onCaptured).toHaveBeenCalledWith(
      expect.objectContaining({ localUri: "file:///cropped.jpg" }),
      "math",
    );
    // The full-resolution capture is deleted once cropped; the crop is the composer's.
    expect(deletedFiles()).toEqual(["file:///shot.jpg"]);
    expect(getByTestId("math-scanner-camera")).toBeTruthy();
    expect(queryByTestId("math-scanner-preview")).toBeNull();
  });

  it("starts math OCR review immediately after a camera capture", async () => {
    const read = jest.fn(async () => ({
      reading: "2x + 3 = 7",
      uncertain: false,
      source: "mathpix" as const,
    }));
    const view = await render(
      <MathEquationScanner
        visible
        onClose={jest.fn()}
        onCaptured={jest.fn()}
        onReadScan={read}
        onSolveReading={jest.fn()}
      />,
    );
    await act(async () => {
      fireEvent.press(view.getByLabelText("chat.math_scan_capture_a11y"));
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(read).toHaveBeenCalledWith(
      expect.objectContaining({ localUri: "file:///cropped.jpg" }),
      "math",
      expect.anything(),
    );
    expect(view.getByTestId("math-scan-review")).toBeTruthy();
    expect(view.queryByTestId("math-scanner-preview")).toBeNull();
  });
});

describe("imported math scanner photos", () => {
  beforeEach(() => {
    mockPermission.granted = true;
    mockPermission.canAskAgain = true;
    jest.spyOn(Dimensions, "get").mockReturnValue({ width: 390, height: 844, scale: 3, fontScale: 1 });
    jest.mocked(pickFromPhotoLibrary).mockResolvedValue({
      localUri: "file:///landscape.png", contentType: "image/png", fileName: "landscape.png", kind: "image",
    });
    jest.mocked(cropScanImage).mockClear();
    jest.mocked(deleteAsync).mockClear();
    mockScanImages();
  });
  afterEach(() => jest.restoreAllMocks());

  it.each([true, false])("shows and sends the whole imported image with camera permission=%s", async (granted) => {
    mockPermission.granted = granted;
    const onCaptured = jest.fn();
    const { getByLabelText, getByTestId, queryByTestId } = await render(
      <MathEquationScanner visible onClose={jest.fn()} onCaptured={onCaptured} />,
    );
    await act(async () => {
      fireEvent.press(getByLabelText("chat.math_scan_photos_a11y"));
    });
    const preview = getByTestId("math-scanner-preview");
    expect(preview.props.resizeMode).toBe("contain");
    expect(preview.props.style.width / preview.props.style.height).toBeCloseTo(1200 / 700, 10);
    expect(queryByTestId("math-scanner-permission")).toBeNull();
    await act(async () => {
      fireEvent.press(getByLabelText("chat.math_scan_solve"));
    });
    expect(cropScanImage).toHaveBeenCalledWith("file:///landscape.png", expect.any(Function));
    const [, cropFor] = jest.mocked(cropScanImage).mock.calls[0];
    expect(cropFor({ width: 1200, height: 700 })).toEqual({ originX: 0, originY: 0, width: 1200, height: 700 });
    expect(onCaptured).toHaveBeenCalledWith(
      expect.objectContaining({ localUri: "file:///cropped.jpg" }),
      "math",
    );
  });

  async function cropForReview(
    read: jest.Mock,
    extra: Partial<React.ComponentProps<typeof MathEquationScanner>> = {},
  ) {
    const onCaptured = jest.fn();
    const onSolveReading = jest.fn();
    const view = await render(
      <MathEquationScanner
        visible
        onClose={jest.fn()}
        onCaptured={onCaptured}
        onReadScan={read}
        onSolveReading={onSolveReading}
        {...extra}
      />,
    );
    await act(async () => {
      fireEvent.press(view.getByLabelText("chat.math_scan_photos_a11y"));
    });
    await act(async () => {
      fireEvent.press(view.getByLabelText("chat.math_scan_solve"));
    });
    return { ...view, onCaptured, onSolveReading };
  }

  it("reads a math crop back and solves the confirmed text", async () => {
    const read = jest.fn(async () => ({ reading: "2x + 3 = 7", uncertain: false, source: "mathpix" }));
    const view = await cropForReview(read);
    expect(read).toHaveBeenCalledWith(
      expect.objectContaining({ localUri: "file:///cropped.jpg" }),
      "math",
      expect.anything(),
    );
    const review = within(view.getByTestId("math-scan-review"));
    await act(async () => {
      fireEvent.changeText(review.getByTestId("math-scan-reading"), "2x + 3 = 11");
    });
    await act(async () => {
      fireEvent.press(review.getByText("chat.math_scan_solve"));
    });
    expect(view.onSolveReading).toHaveBeenCalledWith("2x + 3 = 11", "math");
    expect(view.onCaptured).not.toHaveBeenCalled();
    expect(view.queryByTestId("math-scanner-shutter")).toBeNull();
    expect(view.queryByTestId("math-scanner-preview-retake")).toBeNull();
    expect(view.queryByTestId("math-scanner-preview-solve")).toBeNull();
    expect(view.getByTestId("math-scanner-close")).toBeTruthy();
  });

  it("sends the photo with the reading the student checked", async () => {
    const read = jest.fn(async () => ({ reading: "x^2 = 9", uncertain: true, source: "vision" }));
    const view = await cropForReview(read);
    const review = within(view.getByTestId("math-scan-review"));
    expect(review.getByText("chat.math_scan_uncertain")).toBeTruthy();
    await act(async () => {
      fireEvent.press(review.getByText("chat.math_scan_send_photo"));
    });
    expect(view.onCaptured).toHaveBeenCalledWith(
      expect.objectContaining({ localUri: "file:///cropped.jpg" }),
      "math",
      "x^2 = 9",
    );
  });

  it("shows a rate limit instead of the generic read failure", async () => {
    const read = jest.fn(async () => ({ error: "Too many scans in a row. Try again in a few minutes." }));
    const view = await cropForReview(read);
    expect(
      within(view.getByTestId("math-scan-review")).getByText(
        "Too many scans in a row. Try again in a few minutes.",
      ),
    ).toBeTruthy();
    expect(view.queryByText("chat.math_scan_read_failed")).toBeNull();
  });

  it("does not send a ready reading the student wiped", async () => {
    const read = jest.fn(async () => ({ reading: "2x = 4", uncertain: false, source: "mathpix" as const }));
    const view = await cropForReview(read);
    const review = within(view.getByTestId("math-scan-review"));
    await act(async () => {
      fireEvent.changeText(review.getByTestId("math-scan-reading"), "   ");
    });
    const send = review.getByText("chat.math_scan_send_photo");
    expect(send).toBeDisabled();
    await act(async () => {
      fireEvent.press(send);
    });
    expect(view.onCaptured).not.toHaveBeenCalled();
  });

  it("falls back to the photo when the read fails", async () => {
    const read = jest.fn(async () => null);
    const view = await cropForReview(read);
    const review = within(view.getByTestId("math-scan-review"));
    expect(review.getByText("chat.math_scan_read_failed")).toBeTruthy();
    await act(async () => {
      fireEvent.press(review.getByText("chat.math_scan_send_photo"));
    });
    expect(view.onCaptured).toHaveBeenCalledWith(
      expect.objectContaining({ localUri: "file:///cropped.jpg" }),
      "math",
      undefined,
    );
  });

  it("reads a chemistry crop as text and solves that text alone", async () => {
    const onReadScan = jest.fn(async () => ({
      reading: "Find the molar mass of H2O",
      uncertain: false,
      source: "vision" as const,
    }));
    const onCaptured = jest.fn();
    const onSolveReading = jest.fn();
    const view = await render(
      <MathEquationScanner
        visible
        onClose={jest.fn()}
        onCaptured={onCaptured}
        onReadScan={onReadScan}
        onSolveReading={onSolveReading}
      />,
    );
    await act(async () => {
      fireEvent.press(view.getByTestId("scanner-subject-chemistry"));
    });
    await act(async () => {
      fireEvent.press(view.getByLabelText("chat.math_scan_photos_a11y"));
    });
    await act(async () => {
      fireEvent.press(view.getByLabelText("chat.math_scan_solve"));
    });
    expect(onReadScan).toHaveBeenCalledTimes(1);
    expect(onReadScan).toHaveBeenCalledWith(expect.anything(), "chemistry", expect.anything());
    const review = within(view.getByTestId("math-scan-review"));
    await act(async () => {
      fireEvent.press(review.getByText("chat.math_scan_solve"));
    });
    expect(onSolveReading).toHaveBeenCalledWith("Find the molar mass of H2O", "chemistry");
    expect(onCaptured).not.toHaveBeenCalled();
  });

  it("sends the chemistry photo with the reading the student checked", async () => {
    const onCaptured = jest.fn();
    const view = await render(
      <MathEquationScanner
        visible
        onClose={jest.fn()}
        onCaptured={onCaptured}
        onReadScan={jest.fn(async () => ({
          reading: "Find the molar mass of H2O",
          uncertain: false,
          source: "vision" as const,
        }))}
        onSolveReading={jest.fn()}
      />,
    );
    await act(async () => {
      fireEvent.press(view.getByTestId("scanner-subject-chemistry"));
    });
    await act(async () => {
      fireEvent.press(view.getByLabelText("chat.math_scan_photos_a11y"));
    });
    await act(async () => {
      fireEvent.press(view.getByLabelText("chat.math_scan_solve"));
    });
    const review = within(view.getByTestId("math-scan-review"));
    await act(async () => {
      fireEvent.press(review.getByText("chat.math_scan_send_photo"));
    });
    expect(onCaptured).toHaveBeenCalledWith(
      expect.objectContaining({ localUri: "file:///cropped.jpg" }),
      "chemistry",
      "Find the molar mass of H2O",
    );
  });

  it("sends the chemistry photo when the read fails", async () => {
    const onCaptured = jest.fn();
    const view = await render(
      <MathEquationScanner
        visible
        onClose={jest.fn()}
        onCaptured={onCaptured}
        onReadScan={jest.fn(async () => null)}
        onSolveReading={jest.fn()}
      />,
    );
    await act(async () => {
      fireEvent.press(view.getByTestId("scanner-subject-chemistry"));
    });
    await act(async () => {
      fireEvent.press(view.getByLabelText("chat.math_scan_photos_a11y"));
    });
    await act(async () => {
      fireEvent.press(view.getByLabelText("chat.math_scan_solve"));
    });
    const review = within(view.getByTestId("math-scan-review"));
    expect(review.getByText("chat.math_scan_read_failed")).toBeTruthy();
    await act(async () => {
      fireEvent.press(review.getByText("chat.math_scan_send_photo"));
    });
    expect(onCaptured).toHaveBeenCalledTimes(1);
    expect(onCaptured).toHaveBeenCalledWith(
      expect.objectContaining({ localUri: "file:///cropped.jpg" }),
      "chemistry",
      undefined,
    );
  });

  it("retakes from the review back to the camera", async () => {
    const read = jest.fn(async () => ({ reading: "2x = 4", uncertain: false, source: "mathpix" }));
    const view = await cropForReview(read);
    await act(async () => {
      fireEvent.press(within(view.getByTestId("math-scan-review")).getByText("chat.math_scan_retake"));
    });
    expect(view.queryByTestId("math-scan-review")).toBeNull();
    expect(view.queryByTestId("math-scanner-preview")).toBeNull();
    expect(view.onCaptured).not.toHaveBeenCalled();
  });

  async function scanSubject(subject: string, read: jest.Mock) {
    const onCaptured = jest.fn();
    const onSolveReading = jest.fn();
    const view = await render(
      <MathEquationScanner
        visible
        onClose={jest.fn()}
        onCaptured={onCaptured}
        onReadScan={read}
        onSolveReading={onSolveReading}
      />,
    );
    await act(async () => {
      fireEvent.press(view.getByTestId(`scanner-subject-${subject}`));
    });
    await act(async () => {
      fireEvent.press(view.getByLabelText("chat.math_scan_photos_a11y"));
    });
    await act(async () => {
      fireEvent.press(view.getByLabelText("chat.math_scan_solve"));
    });
    return { ...view, onCaptured, onSolveReading };
  }

  const PHYSICS_READING = "A ball is dropped from 80 m. Find its speed just before it hits the ground.";

  it("reads a physics crop back and solves the confirmed text", async () => {
    const read = jest.fn(async () => ({ reading: PHYSICS_READING, uncertain: false, source: "vision" }));
    const view = await scanSubject("physics", read);
    expect(read).toHaveBeenCalledWith(expect.anything(), "physics", expect.anything());
    const review = within(view.getByTestId("math-scan-review"));
    await act(async () => {
      fireEvent.press(review.getByText("chat.math_scan_solve"));
    });
    expect(view.onSolveReading).toHaveBeenCalledWith(PHYSICS_READING, "physics");
    expect(view.onCaptured).not.toHaveBeenCalled();
  });

  it("sends the physics photo with the reading the student checked", async () => {
    const read = jest.fn(async () => ({ reading: PHYSICS_READING, uncertain: false, source: "vision" }));
    const view = await scanSubject("physics", read);
    await act(async () => {
      fireEvent.press(within(view.getByTestId("math-scan-review")).getByText("chat.math_scan_send_photo"));
    });
    expect(view.onCaptured).toHaveBeenCalledWith(
      expect.objectContaining({ localUri: "file:///cropped.jpg" }),
      "physics",
      PHYSICS_READING,
    );
  });

  it("sends biology photos straight through without a read", async () => {
    const read = jest.fn(async () => ({ reading: "cell", uncertain: false, source: "vision" }));
    const view = await scanSubject("biology", read);
    expect(read).not.toHaveBeenCalled();
    expect(view.onCaptured).toHaveBeenCalledWith(
      expect.objectContaining({ localUri: "file:///cropped.jpg" }),
      "biology",
    );
  });

  it("keeps manual crop for imported photos while camera captures use the live frame", async () => {
    const view = await render(
      <MathEquationScanner visible onClose={jest.fn()} onCaptured={jest.fn()} />,
    );
    await act(async () => {
      fireEvent.press(view.getByLabelText("chat.math_scan_photos_a11y"));
    });
    expect(view.getByTestId("math-scanner-preview").props.resizeMode).toBe("contain");
    expect(view.getByLabelText("chat.math_scan_frame_a11y")).toBeTruthy();
  });
});

describe("scanner sessions and scan files", () => {
  beforeEach(() => {
    jest.spyOn(Dimensions, "get").mockReturnValue({ width: 390, height: 844, scale: 3, fontScale: 1 });
    mockPermission.granted = true;
    mockTakePictureAsync.mockClear();
    jest.mocked(cropScanImage).mockClear();
    jest.mocked(deleteAsync).mockClear();
    mockScanImages();
    jest.mocked(pickFromPhotoLibrary).mockResolvedValue({
      localUri: "file:///landscape.png", contentType: "image/png", fileName: "landscape.png", kind: "image",
    });
  });

  function deferredPhoto() {
    let resolve: (photo: { uri: string }) => void = () => undefined;
    mockTakePictureAsync.mockImplementationOnce(
      () => new Promise<{ uri: string } | null>((done) => {
        resolve = done;
      }),
    );
    return () => resolve({ uri: "file:///shot.jpg" });
  }

  const reading = { reading: "2x + 3 = 7", uncertain: false, source: "mathpix" as const };

  function scanner() {
    const all = {
      visible: true,
      onClose: jest.fn(),
      onCaptured: jest.fn(),
      onReadScan: jest.fn(async () => reading),
      onSolveReading: jest.fn(),
    };
    const element = (visible = true) => <MathEquationScanner {...all} visible={visible} />;
    return { all, element };
  }

  it.each(["biology", "math"])("drops a %s capture that lands after the scanner closed", async (subject) => {
    const finish = deferredPhoto();
    const { all, element } = scanner();
    const view = await render(element());
    await act(async () => {
      fireEvent.press(view.getByTestId(`scanner-subject-${subject}`));
    });
    await act(async () => {
      fireEvent.press(view.getByLabelText("chat.math_scan_capture_a11y"));
    });
    await view.rerender(element(false));
    await act(async () => {
      finish();
    });
    expect(cropScanImage).not.toHaveBeenCalled();
    expect(all.onCaptured).not.toHaveBeenCalled();
    expect(all.onReadScan).not.toHaveBeenCalled();
    expect(deletedFiles()).toContain("file:///shot.jpg");
  });

  it("drops a crop that finishes after the scanner closed, and deletes it", async () => {
    let finishCrop: () => void = () => undefined;
    jest.mocked(cropScanImage).mockImplementationOnce(
      () => new Promise((done) => {
        finishCrop = () => done({ uri: "file:///cropped.jpg", width: 10, height: 10 });
      }),
    );
    const { all, element } = scanner();
    const view = await render(element());
    await act(async () => {
      fireEvent.press(view.getByLabelText("chat.math_scan_capture_a11y"));
    });
    await view.rerender(element(false));
    await act(async () => {
      finishCrop();
    });
    expect(all.onReadScan).not.toHaveBeenCalled();
    expect(deletedFiles()).toEqual(expect.arrayContaining(["file:///shot.jpg", "file:///cropped.jpg"]));
  });

  it("solves with the subject the crop was read with", async () => {
    const finish = deferredPhoto();
    const { all, element } = scanner();
    const view = await render(element());
    await act(async () => {
      fireEvent.press(view.getByLabelText("chat.math_scan_capture_a11y"));
    });
    await act(async () => {
      fireEvent.press(view.getByTestId("scanner-subject-physics"));
    });
    await act(async () => {
      finish();
    });
    expect(all.onReadScan).toHaveBeenCalledWith(expect.anything(), "math", expect.anything());
    await act(async () => {
      fireEvent.press(within(view.getByTestId("math-scan-review")).getByText("chat.math_scan_solve"));
    });
    expect(all.onSolveReading).toHaveBeenCalledWith("2x + 3 = 7", "math");
  });

  async function reviewImported(element: () => React.ReactElement) {
    const view = await render(element());
    await act(async () => {
      fireEvent.press(view.getByTestId("math-scanner-photos"));
    });
    await act(async () => {
      fireEvent.press(view.getByLabelText("chat.math_scan_solve"));
    });
    return within(view.getByTestId("math-scan-review"));
  }

  it.each([
    ["chat.math_scan_retake", ["file:///cropped.jpg", "file:///landscape.png"]],
    ["chat.math_scan_solve", ["file:///cropped.jpg", "file:///landscape.png"]],
    ["chat.math_scan_send_photo", ["file:///landscape.png"]],
  ])("after %s deletes %j; only a sent crop is kept", async (action, deleted) => {
    const { element } = scanner();
    const review = await reviewImported(() => element());
    await act(async () => {
      fireEvent.press(review.getByText(action));
    });
    expect(deletedFiles().sort()).toEqual(deleted);
  });

  it("deletes every scan file when the scanner closes", async () => {
    const { element } = scanner();
    const view = await render(element());
    await act(async () => {
      fireEvent.press(view.getByTestId("math-scanner-photos"));
    });
    await view.rerender(element(false));
    expect(deletedFiles()).toEqual(["file:///landscape.png"]);
  });

  it("crops once when Solve is tapped twice", async () => {
    const { element } = scanner();
    const view = await render(element());
    await act(async () => {
      fireEvent.press(view.getByTestId("math-scanner-photos"));
    });
    await act(async () => {
      fireEvent.press(view.getByLabelText("chat.math_scan_solve"));
      fireEvent.press(view.getByLabelText("chat.math_scan_solve"));
    });
    expect(cropScanImage).toHaveBeenCalledTimes(1);
  });
});
