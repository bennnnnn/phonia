import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Image,
  type LayoutChangeEvent,
  Platform,
  StyleSheet,
  View,
  useWindowDimensions,
} from "react-native";
import { useCameraPermissions } from "expo-image-picker";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTranslation } from "react-i18next";

import { MathScannerChrome } from "@/features/scanner/components/MathScannerChrome";
import {
  MathScannerCropOverlay,
  type LiveScanFrameStatus,
} from "@/features/scanner/components/MathScannerCropOverlay";
import {
  LiveMathScannerCamera,
  type LiveScannerCameraHandle,
  type LiveScannerDetection,
} from "@/features/scanner/components/LiveMathScannerCamera";
import { ScanReadingReview } from "@/features/scanner/components/ScanReadingReview";
import { ScannerPermission } from "@/features/scanner/components/ScannerPermission";
import { ScannerSubjectGuide } from "@/features/scanner/components/ScannerSubjectGuide";
import { useScanReview } from "@/features/scanner/hooks/useScanReview";
import { useMathScannerCrop } from "@/features/scanner/hooks/useMathScannerCrop";
import type { PendingAttachment } from "@/features/attachments/model/attachments";
import type { ScanReading } from "@/lib/api";
import type { ReadBackSubject } from "@/features/scanner/model/readBack";
import {
  NativePickerBusyError,
  NativePickerTimeoutError,
  pickFromPhotoLibrary,
  pickImageDocument,
} from "@/features/attachments/model/attachments";
import { impactMedium, selection } from "@/lib/haptics";
import { useReduceMotion } from "@/lib/motion";
import {
  containedPhotoRegion,
  defaultScanRegion,
  regionToContainedImageCrop,
  regionToImageCrop,
  regionsClose,
  scanChromeInset,
  type ScanRegion,
} from "@/lib/math/scannerRegion";
import { cropScanImage, measureScanImage, ScanFiles } from "@/features/scanner/model/scanImage";
import {
  playScannerSwitchCue,
  stopScannerSwitchCue,
} from "@/features/scanner/model/switchCue";
import { SCANNER_SUBJECTS, type ScannerSubject } from "@/lib/scanner/subjects";
import { scheduleIdlePromise } from "@/lib/scheduleIdle";
import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";
import { FullScreenModal } from "@/ui/overlay/FullScreenModal";

type Props = {
  visible: boolean;
  onClose: () => void;
  /** Send the photo; ``confirmedReading`` when the student checked the read. The composer then owns the file. */
  onCaptured: (
    pending: PendingAttachment,
    subject: ScannerSubject,
    confirmedReading?: string,
  ) => void;
  /** Read the crop back through the subject's reader. Null means it failed. */
  onReadScan?: (
    scan: PendingAttachment,
    subject: ReadBackSubject,
    signal: AbortSignal,
  ) => Promise<ScanReading | { error: string } | null>;
  /** Solve the confirmed reading as typed text (math asks for steps). */
  onSolveReading?: (reading: string, subject: ScannerSubject) => void;
};

type ScanShot = PendingAttachment & { width: number; height: number };

const ANDROID_DISMISS_MS = 400;

/**
 * Keep the crop frame live over the camera so the student aims before capture.
 * Camera shots are cropped immediately from that live region; imported photos
 * still get an adjustable still-image crop. A math, physics or chemistry crop
 * is then read back ("I read this as") so a misread digit can be fixed before
 * solving.
 *
 * A shot checks after every await that the scanner is still in the session it
 * started in: one that lands after close is dropped and its files deleted.
 */
export function MathEquationScanner({
  visible,
  onClose,
  onCaptured,
  onReadScan,
  onSolveReading,
}: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const windowSize = useWindowDimensions();
  // The camera fills this view; the overlay and the crop map against its measured size.
  const [view, setView] = useState({ width: windowSize.width, height: windowSize.height });
  const handleLayout = useCallback((event: LayoutChangeEvent) => {
    const { width, height } = event.nativeEvent.layout;
    if (!(width > 0 && height > 0)) return;
    setView((current) =>
      current.width === width && current.height === height ? current : { width, height },
    );
  }, []);
  const s = useMemo(() => makeStyles(theme), [theme]);
  const reduceMotion = useReduceMotion();
  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<LiveScannerCameraHandle>(null);
  const [hosted, setHosted] = useState(visible);
  const [busy, setBusy] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<ScanShot | null>(null);
  const [torchOn, setTorchOn] = useState(false);
  const [subject, setSubject] = useState<ScannerSubject>("math");
  const [files] = useState(() => new ScanFiles());
  const { review, deliverShot, clearReview, solve, sendPhoto } = useScanReview({
    visible,
    files,
    onCaptured,
    onReadScan,
    onSolveReading,
  });
  // Bumped on every open and close; work started in an older session is stale.
  const sessionRef = useRef(0);
  const [zoom, setZoom] = useState(0);
  const [cameraReady, setCameraReady] = useState(false);
  const [liveRegion, setLiveRegion] = useState<ScanRegion | null>(null);
  const [liveStatus, setLiveStatus] = useState<LiveScanFrameStatus>("idle");
  const liveReadyRef = useRef(false);
  // One shot at a time: a capture or a preview Solve, never two.
  const shotPendingRef = useRef(false);
  const handleCameraReady = useCallback(() => setCameraReady(true), []);
  const handleCameraError = useCallback(() => setError(t("chat.math_scan_camera_unavailable")), [t]);
  const handleCameraMissing = useCallback(() => setError(t("chat.math_scan_camera_needs_build")), [t]);
  const inset = useMemo(
    () => scanChromeInset(view.width, view.height, insets),
    [view.width, view.height, insets.top, insets.bottom],
  );
  const resetLive = useCallback(() => {
    setLiveStatus("idle");
    liveReadyRef.current = false;
  }, []);
  const handleRegionChange = useCallback((region: ScanRegion) => {
    setLiveRegion((current) => (current && regionsClose(current, region) ? current : region));
    resetLive();
  }, [resetLive]);
  const crop = useMathScannerCrop({
    windowWidth: view.width,
    windowHeight: view.height,
    inset,
    preview: Boolean(preview),
    reduceMotion,
    onZoom: setZoom,
    onRegionChange: handleRegionChange,
  });
  const scanRegion = liveRegion ?? defaultScanRegion(inset);

  const handleLiveDetection = useCallback((detection: LiveScannerDetection) => {
    const next: LiveScanFrameStatus = detection.stable
      ? "ready"
      : detection.hasText
        ? "detecting"
        : "idle";
    setLiveStatus(next);
    if (detection.stable && !liveReadyRef.current) selection();
    liveReadyRef.current = detection.stable;
  }, []);

  const previewFrame = useMemo(
    () => preview
      ? containedPhotoRegion(preview.width, preview.height, view.width, view.height, inset)
      : null,
    [inset, preview, view.height, view.width],
  );
  const resetCropRegion = crop.resetRegion;
  useEffect(() => {
    if (previewFrame) resetCropRegion(previewFrame);
  }, [previewFrame, resetCropRegion]);

  useEffect(() => {
    sessionRef.current += 1;
    if (visible) {
      setHosted(true);
      setPreview(null);
      clearReview();
      setError(null);
      setTorchOn(false);
      setCameraReady(false);
      resetLive();
      crop.resetRegion();
      crop.resetZoom();
      return;
    }
    files.discardAll();
    stopScannerSwitchCue();
    if (Platform.OS === "ios") return;
    const timer = setTimeout(() => setHosted(false), ANDROID_DISMISS_MS);
    return () => clearTimeout(timer);
    // Reset live session when opening; crop helpers are stable enough per open.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- open-only reset
  }, [visible]);

  useEffect(() => () => {
    stopScannerSwitchCue();
    files.discardAll();
  }, [files]);

  /** Show a shot for a manual crop, sized in the space the crop is cut in. */
  const showShot = useCallback(
    async (pending: PendingAttachment, isCurrent: () => boolean) => {
      try {
        const size = await measureScanImage(pending.localUri);
        if (isCurrent()) setPreview({ ...pending, ...size });
        else files.discard(pending.localUri);
      } catch {
        files.discard(pending.localUri);
        if (isCurrent()) setError(t("chat.math_scan_failed"));
      }
    },
    [files, t],
  );

  /** One shot's work, told whether the scanner is still the session it started in. */
  const runShot = useCallback(async (work: (isCurrent: () => boolean) => Promise<void>) => {
    if (shotPendingRef.current) return;
    shotPendingRef.current = true;
    const session = sessionRef.current;
    const isCurrent = () => session === sessionRef.current;
    try {
      await work(isCurrent);
    } catch {
      if (isCurrent()) setError(t("chat.math_scan_failed"));
    } finally {
      shotPendingRef.current = false;
      setBusy(false);
      setCapturing(false);
    }
  }, [t]);

  /** Hand a fresh crop on, unless the scanner closed while it was cut. */
  const deliverCrop = useCallback(
    (cropped: PendingAttachment, shotSubject: ScannerSubject, isCurrent: () => boolean) => {
      files.track(cropped.localUri);
      if (!isCurrent()) {
        files.discard(cropped.localUri);
        return;
      }
      if (deliverShot(cropped, shotSubject)) resetLive();
    },
    [deliverShot, files, resetLive],
  );

  const capture = useCallback(() => {
    // Not ready yet is startup, not a failure. onError already reports a real load failure.
    if (busy || preview || !cameraReady || !cameraRef.current) return;
    const shotSubject = subject;
    const region = crop.readRegion();
    const { width: viewWidth, height: viewHeight } = view;
    void runShot(async (isCurrent) => {
      const camera = cameraRef.current;
      if (!camera) return;
      impactMedium();
      setBusy(true);
      setCapturing(true);
      setError(null);
      const photo = await camera.takePictureAsync();
      if (!photo?.uri) {
        if (isCurrent()) setError(t("chat.math_scan_failed"));
        return;
      }
      files.track(photo.uri);
      if (!isCurrent()) {
        files.discard(photo.uri);
        return;
      }
      const pending: PendingAttachment = {
        localUri: photo.uri,
        contentType: "image/jpeg",
        fileName: `${shotSubject}-scan-${Date.now()}.jpg`,
        kind: "image",
      };
      let cropped: { uri: string };
      try {
        cropped = await cropScanImage(photo.uri, (size) =>
          regionToImageCrop(region, size.width, size.height, viewWidth, viewHeight),
        );
      } catch {
        // Keep a recoverable path if a device reports unexpected camera geometry.
        await showShot(pending, isCurrent);
        return;
      }
      // The full-resolution capture is not needed once it is cropped.
      files.discard(photo.uri);
      deliverCrop({ ...pending, localUri: cropped.uri }, shotSubject, isCurrent);
    });
  }, [busy, cameraReady, crop, deliverCrop, files, preview, runShot, showShot, subject, t, view]);

  const confirmPreview = useCallback(() => {
    if (!preview || busy || !previewFrame) return;
    const shotSubject = subject;
    const region = crop.readRegion();
    void runShot(async (isCurrent) => {
      setBusy(true);
      setError(null);
      const cropped = await cropScanImage(preview.localUri, (size) =>
        regionToContainedImageCrop(region, previewFrame, size.width, size.height),
      );
      deliverCrop(
        { localUri: cropped.uri, contentType: "image/jpeg", fileName: preview.fileName, kind: "image" },
        shotSubject,
        isCurrent,
      );
    });
  }, [busy, crop, deliverCrop, preview, previewFrame, runShot, subject]);

  /** Back to the live camera; every file from the last shot is deleted. */
  const retake = useCallback(() => {
    clearReview();
    files.discardAll();
    resetLive();
    crop.resetRegion();
    setPreview(null);
    setError(null);
  }, [clearReview, crop, files, resetLive]);

  const changeSubject = useCallback((next: ScannerSubject) => {
    if (next === subject) return;
    const currentIndex = SCANNER_SUBJECTS.indexOf(next);
    const previousIndex = SCANNER_SUBJECTS.indexOf(subject);
    selection();
    void playScannerSwitchCue(currentIndex > previousIndex ? 1 : -1);
    resetLive();
    setSubject(next);
  }, [resetLive, subject]);

  /** Photos by default (no permission needed, and where a homework photo is); Files second. */
  const openLibrary = useCallback(async (source: "photos" | "files") => {
    if (busy) return;
    const session = sessionRef.current;
    const isCurrent = () => session === sessionRef.current;
    setBusy(true);
    setError(null);
    try {
      await scheduleIdlePromise();
      const picked = await (source === "files" ? pickImageDocument() : pickFromPhotoLibrary());
      if (!picked) return;
      // The picker copied the image into the cache for the scanner.
      files.track(picked.localUri);
      if (isCurrent()) resetLive();
      await showShot(picked, isCurrent);
    } catch (caught) {
      if (!isCurrent()) return;
      if (caught instanceof NativePickerBusyError || caught instanceof NativePickerTimeoutError) {
        setError(t("chat.picker_busy"));
      } else {
        setError(t("chat.math_scan_failed"));
      }
    } finally {
      setBusy(false);
    }
  }, [busy, files, resetLive, showShot, t]);

  const granted = Boolean(permission?.granted);

  if (!hosted && !visible) return null;

  return (
    <FullScreenModal
      visible={visible}
      animationType="fade"
      presentationStyle="fullScreen"
      statusBarTranslucent
      onRequestClose={onClose}
      onDismiss={() => setHosted(false)}
      testID="math-scanner-modal"
    >
      <GestureHandlerRootView style={s.root} onLayout={handleLayout}>
        {!permission && !preview ? (
          <View style={s.center}>
            <ActivityIndicator color={theme.onMedia} />
          </View>
        ) : !granted && !preview ? (
          <ScannerPermission
            permission={permission}
            requestPermission={() => void requestPermission()}
            onChoosePhoto={() => void openLibrary("photos")}
            onChooseFile={() => void openLibrary("files")}
          />
        ) : (
          <View style={StyleSheet.absoluteFill} collapsable={false}>
            {granted ? <View style={StyleSheet.absoluteFill} testID="math-scanner-camera" pointerEvents="none">
              <LiveMathScannerCamera
                ref={cameraRef}
                active={!preview && !review && visible}
                torchOn={torchOn && !preview && !review && visible}
                zoom={zoom}
                scanRegion={scanRegion}
                viewSize={view}
                onReady={handleCameraReady}
                onError={handleCameraError}
                onUnavailable={handleCameraMissing}
                onDetectionChange={handleLiveDetection}
              />
            </View> : null}
            {granted && !preview && !review ? <ScannerSubjectGuide subject={subject} /> : null}
            {preview ? (
              <View style={[StyleSheet.absoluteFill, { backgroundColor: theme.mediaScrim }]}>
                <Image
                  source={{ uri: preview.localUri }}
                  testID="math-scanner-preview"
                  style={previewFrame ? {
                    position: "absolute",
                    left: previewFrame.x * view.width,
                    top: previewFrame.y * view.height,
                    width: previewFrame.width * view.width,
                    height: previewFrame.height * view.height,
                  } : StyleSheet.absoluteFill}
                  resizeMode="contain"
                />
              </View>
            ) : null}
            {preview || (granted && !review) ? (
              <MathScannerCropOverlay
                regionGesture={crop.regionGesture}
                cornerTL={crop.cornerTL}
                cornerTR={crop.cornerTR}
                cornerBL={crop.cornerBL}
                cornerBR={crop.cornerBR}
                regionStyle={crop.regionStyle}
                maskTopStyle={crop.maskTopStyle}
                maskBottomStyle={crop.maskBottomStyle}
                maskLeftStyle={crop.maskLeftStyle}
                maskRightStyle={crop.maskRightStyle}
                handleTLStyle={crop.handleTLStyle}
                handleTRStyle={crop.handleTRStyle}
                handleBLStyle={crop.handleBLStyle}
                handleBRStyle={crop.handleBRStyle}
                scanning={Boolean(preview) && !busy}
                liveStatus={preview ? "idle" : liveStatus}
                onGrow={crop.growRegion}
                onShrink={crop.shrinkRegion}
              />
            ) : null}
          </View>
        )}
        <MathScannerChrome
          insets={insets}
          granted={granted}
          preview={Boolean(preview)}
          busy={busy}
          capturing={capturing}
          captureReady={cameraReady}
          torchOn={torchOn}
          subject={subject}
          error={error}
          onClose={onClose}
          onSubjectChange={changeSubject}
          onToggleTorch={() => {
            selection();
            setTorchOn((on) => !on);
          }}
          onOpenPhotos={() => void openLibrary("photos")}
          onOpenFiles={() => void openLibrary("files")}
          onCapture={capture}
          onRetake={retake}
          onSolve={confirmPreview}
          reviewing={review !== null}
        />
        {review ? (
          <ScanReadingReview
            photoUri={review.shot.localUri}
            state={review.state}
            insets={insets}
            onSolve={solve}
            onSendPhoto={sendPhoto}
            onRetake={retake}
          />
        ) : null}
      </GestureHandlerRootView>
    </FullScreenModal>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    root: {
      flex: 1,
      backgroundColor: theme.mediaScrim,
    },
    center: {
      flex: 1,
      alignItems: "center",
      justifyContent: "center",
      paddingHorizontal: Space.xl,
      gap: Space.md,
    },
  });
}
