import React from "react";
import { act, render } from "@testing-library/react-native";

import { LiveMathScannerCamera } from "@/features/scanner/components/LiveMathScannerCamera";

// Expo Go and older dev clients have no VisionCamera: loading the native camera throws.
jest.mock("@/features/scanner/components/LiveMathScannerCameraNative", () => {
  throw new Error("NitroModules are not available in Expo Go");
});

it("reports a build without the native camera as unavailable, not as a camera error", async () => {
  const onUnavailable = jest.fn();
  const onError = jest.fn();
  const props = {
    active: true,
    torchOn: false,
    zoom: 0,
    scanRegion: { x: 0.1, y: 0.3, width: 0.8, height: 0.3 },
    viewSize: { width: 390, height: 844 },
    onReady: jest.fn(),
    onError,
    onDetectionChange: jest.fn(),
  };
  const view = await render(<LiveMathScannerCamera {...props} onUnavailable={onUnavailable} />);
  await act(async () => {
    await Promise.resolve();
  });
  // A new handler identity must not load the camera again.
  await view.rerender(<LiveMathScannerCamera {...props} onUnavailable={jest.fn()} />);
  await act(async () => {
    await Promise.resolve();
  });
  expect(onUnavailable).toHaveBeenCalledTimes(1);
  expect(onError).not.toHaveBeenCalled();
});
