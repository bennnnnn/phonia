/**
 * The waiting card's moving wave without Skia (Expo Go, or a build whose
 * native Skia the repo probe rejects). Three layers:
 *
 * 1. the resting dot color, filling the card;
 * 2. a strip of soft accent bands (an SVG gradient, wider than the card),
 *    tilted down-right and slid along its length by Reanimated on the UI
 *    thread, one period per WAVE_SWEEP_MS so the loop has no seam;
 * 3. a still SVG cover in the card's color with a hole at every dot.
 *
 * The bands show only through the holes, so the dots brighten as a band
 * passes. Unlike the shader they do not grow. No React render per frame.
 */
import { useEffect, useId, useMemo } from "react";
import { StyleSheet, View } from "react-native";
import Svg, { Defs, LinearGradient, Path, Rect, Stop } from "react-native-svg";
import Animated, {
  cancelAnimation,
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
} from "react-native-reanimated";

import { dotGridLayout, dotHolesPath } from "@/features/images/model/dotGrid";
import { waveBandLayout, waveBandStops } from "@/features/images/model/dotWaveBand";
import { withAlpha } from "@/lib/theme";

import { type DotFieldPalette, WAVE_DOT_RADIUS, WAVE_PITCH } from "./dotField";

/** One band crosses the card in this time (the shader's pace). */
const WAVE_SWEEP_MS = 5000;

type Props = {
  width: number;
  height: number;
  palette: DotFieldPalette;
  /** The card's fill: the cover is this color, so it reads as the card. */
  cardColor: string;
};

export function DotCutoutWave({ width, height, palette, cardColor }: Props) {
  const gradientId = `band${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const holes = useMemo(
    () => dotHolesPath(dotGridLayout(width, height, WAVE_PITCH), width, height, WAVE_DOT_RADIUS),
    [width, height],
  );
  const band = useMemo(() => waveBandLayout(width, height), [width, height]);
  const stops = useMemo(
    () => waveBandStops(band, palette.accent.opacity),
    [band, palette.accent.opacity],
  );
  const s = useMemo(
    () =>
      StyleSheet.create({
        base: { backgroundColor: withAlpha(palette.dot.color, palette.dot.opacity) },
        strip: {
          position: "absolute",
          left: band.left,
          top: band.top,
          width: band.width,
          height: band.height,
        },
      }),
    [band, palette.dot.color, palette.dot.opacity],
  );

  const progress = useSharedValue(0);
  useEffect(() => {
    progress.value = 0;
    progress.value = withRepeat(
      withTiming(1, { duration: WAVE_SWEEP_MS, easing: Easing.linear }),
      -1,
      false,
    );
    return () => cancelAnimation(progress);
  }, [progress]);

  const { period, angleDeg } = band;
  const slideStyle = useAnimatedStyle(() => ({
    transform: [
      { rotate: `${angleDeg}deg` },
      { translateX: -period / 2 + progress.value * period },
    ],
  }));

  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="none" testID="image-gen-dots-cutout">
      <View style={[StyleSheet.absoluteFill, s.base]} />
      <Animated.View style={[s.strip, slideStyle]} testID="image-gen-wave-band">
        <Svg width={band.width} height={band.height}>
          <Defs>
            <LinearGradient id={gradientId} x1="0" y1="0" x2="1" y2="0">
              {stops.map((stop, index) => (
                <Stop
                  key={index}
                  offset={stop.offset}
                  stopColor={palette.accent.color}
                  stopOpacity={stop.opacity}
                />
              ))}
            </LinearGradient>
          </Defs>
          <Rect width={band.width} height={band.height} fill={`url(#${gradientId})`} />
        </Svg>
      </Animated.View>
      <Svg
        width={width}
        height={height}
        style={StyleSheet.absoluteFill}
        testID="image-gen-wave-holes"
      >
        <Path d={holes} fill={cardColor} fillRule="evenodd" />
      </Svg>
    </View>
  );
}
