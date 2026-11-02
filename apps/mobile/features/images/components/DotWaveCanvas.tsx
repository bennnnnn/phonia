/**
 * The waiting card's moving dot field, drawn by one Skia shader
 * (`DOT_WAVE_SKSL` in `dotField.ts`). The only thing that changes per frame
 * is the `uTime` uniform: a Reanimated value looping 0 → DOT_WAVE_LOOP_S on
 * the UI thread, so the wave runs without JS work or React renders.
 *
 * Loaded lazily (Skia's JS is large) and only after `dotWaveEffect()` has
 * passed the repo's `isSkiaAvailable()` probe and compiled the shader, so it
 * never mounts in Expo Go or a build without Skia (`DotCutoutWave` instead).
 */
import { useEffect, useMemo } from "react";
import { PixelRatio, StyleSheet } from "react-native";
import { Canvas, Fill, Shader, Skia } from "@shopify/react-native-skia";
import {
  cancelAnimation,
  Easing,
  useDerivedValue,
  useSharedValue,
  withRepeat,
  withTiming,
} from "react-native-reanimated";

import { dotGridLayout } from "@/features/images/model/dotGrid";

import {
  type DotFieldPalette,
  type DotInk,
  DOT_WAVE_LOOP_S,
  dotWaveEffect,
  WAVE_DOT_RADIUS,
  WAVE_PITCH,
  WAVE_SWELL,
} from "./dotField";

type Props = { width: number; height: number; palette: DotFieldPalette };

/** Straight (not premultiplied) RGBA 0–1; the shader premultiplies. */
function inkUniform(ink: DotInk): number[] {
  const [r = 0, g = 0, b = 0, a = 1] = Array.from(Skia.Color(ink.color));
  return [r, g, b, a * ink.opacity];
}

export default function DotWaveCanvas({ width, height, palette }: Props) {
  const effect = dotWaveEffect();
  const time = useSharedValue(0);

  useEffect(() => {
    time.value = 0;
    time.value = withRepeat(
      withTiming(DOT_WAVE_LOOP_S, {
        duration: DOT_WAVE_LOOP_S * 1000,
        easing: Easing.linear,
      }),
      -1,
      false,
    );
    return () => cancelAnimation(time);
  }, [time]);

  const still = useMemo(() => {
    const grid = dotGridLayout(width, height, WAVE_PITCH);
    return {
      uSize: [width, height],
      uOrigin: [grid.originX, grid.originY],
      uCount: [grid.cols, grid.rows],
      uPitch: grid.pitch,
      uRadius: WAVE_DOT_RADIUS,
      uSwell: WAVE_SWELL,
      // About three quarters of a device pixel of edge softening.
      uAa: 0.75 / PixelRatio.get(),
      uBase: inkUniform(palette.dot),
      uAccent: inkUniform(palette.accent),
    };
  }, [width, height, palette]);

  const uniforms = useDerivedValue(() => ({ ...still, uTime: time.value }), [still]);

  if (!effect) return null;
  return (
    <Canvas style={StyleSheet.absoluteFill} testID="image-gen-dots-wave">
      <Fill>
        <Shader source={effect} uniforms={uniforms} />
      </Fill>
    </Canvas>
  );
}
