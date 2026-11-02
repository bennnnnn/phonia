import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { StyleSheet, View } from "react-native";

import type {
  LiveScannerCameraHandle,
  LiveScannerCameraProps,
  LiveScannerDetection,
} from "@/features/scanner/components/LiveMathScannerCameraNative";

export type { LiveScannerCameraHandle, LiveScannerDetection };

type NativeCamera =
  typeof import("@/features/scanner/components/LiveMathScannerCameraNative").LiveMathScannerCameraNative;

type Props = LiveScannerCameraProps & {
  /** The native camera is not in this build (Expo Go, or a dev client built before it). */
  onUnavailable: () => void;
};

/**
 * Loads the live scanner only after this view mounts. A static import pulls in
 * VisionCamera and Nitro, which crashes chat in Expo Go and in a dev client
 * built before that camera library existed. There the import fails, and the
 * scanner says the live camera needs a newer build instead of a camera error.
 */
export const LiveMathScannerCamera = forwardRef<LiveScannerCameraHandle, Props>(
  function LiveMathScannerCamera({ onUnavailable, ...props }, ref) {
    const nativeRef = useRef<LiveScannerCameraHandle>(null);
    const [Native, setNative] = useState<NativeCamera | null>(null);
    const onUnavailableRef = useRef(onUnavailable);
    useEffect(() => {
      onUnavailableRef.current = onUnavailable;
    }, [onUnavailable]);

    useImperativeHandle(
      ref,
      () => ({
        async takePictureAsync() {
          return (await nativeRef.current?.takePictureAsync()) ?? null;
        },
      }),
      [],
    );

    useEffect(() => {
      let cancelled = false;
      import("@/features/scanner/components/LiveMathScannerCameraNative")
        .then((mod) => {
          if (!cancelled) setNative(() => mod.LiveMathScannerCameraNative);
        })
        .catch(() => {
          if (!cancelled) {
            setNative(null);
            onUnavailableRef.current();
          }
        });
      return () => {
        cancelled = true;
      };
    }, []);

    if (!Native) return <View style={StyleSheet.absoluteFill} />;

    return <Native ref={nativeRef} {...props} />;
  },
);
