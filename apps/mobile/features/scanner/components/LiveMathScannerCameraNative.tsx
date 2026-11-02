import {
  forwardRef,
  useCallback,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import { StyleSheet, View } from "react-native";
import {
  Camera,
  CommonResolutions,
  useCameraDevice,
  useFrameOutput,
  usePhotoOutput,
} from "react-native-vision-camera";
import {
  useTextRecognition,
  type RegionOfInterest,
} from "react-native-vision-camera-mlkit";
import { createSynchronizable, scheduleOnRN } from "react-native-worklets";

import { type ScanRegion, viewRegionToImageRegion } from "@/lib/math/scannerRegion";
import { LIVE_READ_INTERVAL_MS, shouldReadFrame } from "@/features/scanner/model/frameThrottle";
import { hasUsefulScannerText, normalizeLiveText } from "@/features/scanner/model/liveText";

export type LiveScannerDetection = {
  hasText: boolean;
  stable: boolean;
  text: string;
};

export type LiveScannerCameraHandle = {
  /** A full-resolution capture in the cache; the caller deletes it. */
  takePictureAsync: () => Promise<{ uri: string } | null>;
};

export type LiveScannerCameraProps = {
  active: boolean;
  torchOn: boolean;
  zoom: number;
  /** The crop frame, as ratios of the view the preview covers. */
  scanRegion: ScanRegion;
  /** The measured size of the view the preview covers. */
  viewSize: Size;
  onReady: () => void;
  onError: () => void;
  onDetectionChange: (detection: LiveScannerDetection) => void;
};

type Size = { width: number; height: number };

const STABLE_FRAMES = 3;
const FRAME_RESOLUTION = CommonResolutions.VGA_16_9;

/** The app is portrait-only, so an upright frame is the taller way round. */
function uprightSize(width: number, height: number): Size {
  return { width: Math.min(width, height), height: Math.max(width, height) };
}
const MAX_SCANNER_ZOOM = 6;

/**
 * Native VisionCamera preview + low-resolution ML Kit frame OCR.
 *
 * The live OCR is only a targeting signal. Recall still performs the final,
 * high-quality Mathpix/vision read after capture, so live frames never hit a
 * paid cloud OCR endpoint.
 */
export const LiveMathScannerCameraNative = forwardRef<LiveScannerCameraHandle, LiveScannerCameraProps>(
  function LiveMathScannerCameraNative(
    {
      active,
      torchOn,
      zoom,
      scanRegion,
      viewSize,
      onReady,
      onError,
      onDetectionChange,
    },
    ref,
  ) {
    const device = useCameraDevice("back");
    const photoOutput = usePhotoOutput({
      targetResolution: CommonResolutions.UHD_4_3,
      containerFormat: "jpeg",
      quality: 0.92,
      qualityPrioritization: "balanced",
    });
    const [frameSize, setFrameSize] = useState<Size>(() =>
      uprightSize(FRAME_RESOLUTION.width, FRAME_RESOLUTION.height),
    );
    // The preview covers the view, so the frame's hidden overflow is mapped
    // out exactly as the capture crop maps it.
    const roi = useMemo<RegionOfInterest>(
      () => ({
        ...viewRegionToImageRegion(
          scanRegion,
          frameSize.width,
          frameSize.height,
          viewSize.width,
          viewSize.height,
        ),
        unit: "normalized",
      }),
      [frameSize, scanRegion, viewSize.height, viewSize.width],
    );
    const { textRecognition } = useTextRecognition({
      language: "LATIN",
      roi,
      scaleFactor: 0.92,
    });
    // When the camera thread last read a frame; it checks and sets this frame to frame,
    // as VisionCamera's own async runner keeps its busy flag.
    const lastReadAt = useMemo(() => createSynchronizable(0), []);
    const lastTextRef = useRef("");
    const stableCountRef = useRef(0);
    const lastDetectionKeyRef = useRef("");

    const publishFrameText = useCallback(
      (rawText: string, frameWidth: number, frameHeight: number) => {
        const upright = uprightSize(frameWidth, frameHeight);
        setFrameSize((current) =>
          current.width === upright.width && current.height === upright.height ? current : upright,
        );
        const normalized = normalizeLiveText(rawText);
        const hasText = hasUsefulScannerText(rawText);

        if (!hasText) {
          lastTextRef.current = "";
          stableCountRef.current = 0;
        } else if (normalized === lastTextRef.current) {
          stableCountRef.current += 1;
        } else {
          lastTextRef.current = normalized;
          stableCountRef.current = 1;
        }

        const stable = hasText && stableCountRef.current >= STABLE_FRAMES;
        const key = `${hasText ? 1 : 0}:${stable ? 1 : 0}:${normalized}`;
        if (key === lastDetectionKeyRef.current) return;
        lastDetectionKeyRef.current = key;
        onDetectionChange({ hasText, stable, text: rawText.trim() });
      },
      [onDetectionChange],
    );

    const frameOutput = useFrameOutput({
      targetResolution: FRAME_RESOLUTION,
      pixelFormat: "yuv",
      dropFramesWhileBusy: true,
      onFrameDropped: () => undefined,
      onFrame(frame) {
        "worklet";
        try {
          const now = Date.now();
          if (!shouldReadFrame(lastReadAt.getDirty(), now, LIVE_READ_INTERVAL_MS)) return;
          lastReadAt.setBlocking(now);
          const result = textRecognition(frame, { outputOrientation: "portrait" });
          scheduleOnRN(publishFrameText, result.text, frame.width, frame.height);
        } finally {
          frame.dispose();
        }
      },
    });

    const outputs = useMemo(
      () => [photoOutput, frameOutput],
      [frameOutput, photoOutput],
    );
    const constraints = useMemo(() => [{ fps: 30 }], []);

    const cameraZoom = useMemo(() => {
      if (!device) return 1;
      const neutral = Math.min(device.maxZoom, Math.max(device.minZoom, 1));
      const max = Math.max(neutral, Math.min(device.maxZoom, MAX_SCANNER_ZOOM));
      return neutral + Math.min(1, Math.max(0, zoom)) * (max - neutral);
    }, [device, zoom]);

    useImperativeHandle(
      ref,
      () => ({
        async takePictureAsync() {
          if (!device || !active) return null;
          const photo = await photoOutput.capturePhotoToFile(
            {
              flashMode: "off",
              enableShutterSound: true,
              enableDistortionCorrection: device.supportsDistortionCorrection,
            },
            {},
          );
          return {
            uri: `file://${photo.filePath}`,
          };
        },
      }),
      [active, device, photoOutput],
    );

    if (!device) {
      return <View style={StyleSheet.absoluteFill} />;
    }

    return (
      <Camera
        style={StyleSheet.absoluteFill}
        device={device}
        isActive={active}
        outputs={outputs}
        constraints={constraints}
        orientationSource="interface"
        zoom={cameraZoom}
        torchMode={torchOn && device.hasTorch ? "on" : "off"}
        enableSmoothAutoFocus
        onStarted={onReady}
        onError={onError}
      />
    );
  },
);
