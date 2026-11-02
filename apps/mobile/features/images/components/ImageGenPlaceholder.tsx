import { lazy, memo, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useTranslation } from "react-i18next";

import { useThumbnailSize } from "@/features/attachments/components/ChatMessageImage";
import {
  estimateImageGenPercent,
  imageGenStageIndex,
} from "@/features/images/model/imageGenProgress";
import { tap } from "@/lib/haptics";
import { useReduceMotion } from "@/lib/motion";
import { Radius } from "@/lib/radius";
import { shadowRaised } from "@/lib/shadow";
import { Space } from "@/lib/space";
import { streamStatusLabels } from "@/lib/streamStatusLabel";
import { Theme, useTheme } from "@/lib/theme";
import { DYNAMIC_TYPE_MAX, Type, Weight } from "@/lib/type";
import { Button } from "@/ui/controls/Button";

import { DotCutoutWave } from "./DotCutoutWave";
import { StaticDotField } from "./DotGridSvg";
import { DotSnakePlay } from "./DotSnakePlay";
import { type DotFieldPalette, dotFieldPalette, dotWaveEffect } from "./dotField";
import { StageLine } from "./StageLine";

const DotWaveCanvas = lazy(() => import("./DotWaveCanvas"));

/** How often the estimated percentage is recomputed. */
const PROGRESS_TICK_MS = 250;

type Props = {
  /** Replaces the stage line, e.g. the failure message on a settled card. */
  statusText?: string | null;
  outcome?: "pending" | "canceled" | "failed";
  onRetry?: () => void;
};

/**
 * The image-gen waiting card. A short stage line ("Sketching it out") sits
 * above a card the size of the finished thumbnail, so the image swaps in
 * without a layout jump. The card is a fine dot grid with a slow accent wave
 * (a Skia shader, or a Skia-free cutout in Expo Go) and an estimated
 * percentage; a tap turns it into a little dot game until the image arrives.
 * A canceled or failed card keeps still dots, says what happened, and offers
 * Retry.
 */
export const ImageGenPlaceholder = memo(function ImageGenPlaceholder({
  statusText,
  outcome = "pending",
  onRetry,
}: Props) {
  const { t } = useTranslation();
  const C = useTheme();
  const reduceMotion = useReduceMotion();
  const { width, height } = useThumbnailSize();
  const s = useMemo(() => makeStyles(C, width, height), [C, width, height]);
  const palette = useMemo(() => dotFieldPalette(C), [C]);
  const pending = outcome === "pending";
  const percent = useEstimatedPercent(pending);
  const [playing, setPlaying] = useState(false);
  const isPlaying = pending && playing;

  const stages = useMemo(() => streamStatusLabels(t, "image_gen"), [t]);
  const fallback =
    outcome === "canceled"
      ? t("chat.image_gen_canceled")
      : outcome === "failed"
        ? t("chat.image_gen_failed")
        : t("chat.status.image_gen");
  const stage =
    statusText?.trim() ||
    (pending ? stages[imageGenStageIndex(percent, stages.length)] : undefined) ||
    fallback;
  const percentLabel = t("chat.image_gen_percent", { percent });
  const cardLabel = pending
    ? t("chat.image_gen_a11y_progress", { status: stage, percent: percentLabel })
    : stage;

  const startPlay = useCallback(() => {
    tap();
    setPlaying(true);
  }, []);
  const stopPlay = useCallback(() => setPlaying(false), []);

  return (
    <View style={s.root}>
      <StageLine label={stage} shimmer={pending} testID="image-gen-stage" />
      <View style={s.card} testID="image-gen-card">
        {isPlaying ? (
          <DotSnakePlay
            width={width}
            height={height}
            palette={palette}
            cardColor={C.surface}
            eyeColor={C.onPrimary}
            accessibilityLabel={cardLabel}
            onStop={stopPlay}
          />
        ) : (
          <>
            <View
              style={StyleSheet.absoluteFill}
              accessible
              accessibilityRole="image"
              accessibilityLabel={cardLabel}
              testID="image-gen-dots"
            >
              <DotField
                width={width}
                height={height}
                palette={palette}
                cardColor={C.surface}
                animate={pending && !reduceMotion}
              />
            </View>
            {pending ? (
              <Pressable
                style={StyleSheet.absoluteFill}
                onPress={startPlay}
                accessibilityRole="button"
                accessibilityLabel={t("chat.image_gen_play")}
                accessibilityHint={t("chat.image_gen_play_hint")}
                accessibilityState={{ selected: false }}
                testID="image-gen-play"
              />
            ) : null}
          </>
        )}
        {pending ? (
          <View
            style={s.pill}
            pointerEvents="none"
            accessibilityElementsHidden
            importantForAccessibility="no-hide-descendants"
            testID="image-gen-progress"
          >
            <Text style={s.pillLabel} maxFontSizeMultiplier={DYNAMIC_TYPE_MAX}>
              {percentLabel}
            </Text>
          </View>
        ) : onRetry ? (
          <View style={s.retryWrap} pointerEvents="box-none">
            <Button
              title={t("common.retry")}
              onPress={onRetry}
              variant="secondary"
              size="sm"
              style={s.retry}
              testID="image-gen-retry"
            />
          </View>
        ) : null}
      </View>
    </View>
  );
});

type DotFieldProps = {
  width: number;
  height: number;
  palette: DotFieldPalette;
  cardColor: string;
  animate: boolean;
};

/**
 * Still dots for a settled card or under Reduce Motion. Otherwise the wave:
 * the Skia shader where the repo probe allows Skia (still dots while its code
 * loads), and the Skia-free cutout wave everywhere else, Expo Go included.
 */
function DotField({ width, height, palette, cardColor, animate }: DotFieldProps) {
  const still = <StaticDotField width={width} height={height} palette={palette} />;
  if (!animate) return still;
  if (!dotWaveEffect()) {
    return (
      <DotCutoutWave width={width} height={height} palette={palette} cardColor={cardColor} />
    );
  }
  return (
    <Suspense fallback={still}>
      <DotWaveCanvas width={width} height={height} palette={palette} />
    </Suspense>
  );
}

/**
 * Estimated percent since this card first went pending. The server sends no
 * progress, so this eases toward 95 (`estimateImageGenPercent`).
 */
function useEstimatedPercent(active: boolean): number {
  const startedAt = useRef<number | null>(null);
  const [percent, setPercent] = useState(() => estimateImageGenPercent(0));

  useEffect(() => {
    if (!active) return;
    const start = startedAt.current ?? Date.now();
    startedAt.current = start;
    const id = setInterval(() => {
      setPercent(estimateImageGenPercent(Date.now() - start));
    }, PROGRESS_TICK_MS);
    return () => clearInterval(id);
  }, [active]);

  return percent;
}

function makeStyles(C: Theme, width: number, height: number) {
  return StyleSheet.create({
    root: {
      alignItems: "flex-start",
      gap: Space.xs,
    },
    card: {
      width,
      height,
      borderRadius: Radius.bubble,
      overflow: "hidden",
      backgroundColor: C.surface,
    },
    pill: {
      position: "absolute",
      right: Space.xs,
      bottom: Space.xs,
      paddingHorizontal: Space.xs,
      paddingVertical: 2,
      borderRadius: Radius.full,
      backgroundColor: C.elevated,
      ...shadowRaised(C),
    },
    pillLabel: {
      ...Type.compact,
      ...Weight.semibold,
      color: C.accent,
      fontVariant: ["tabular-nums"],
    },
    retryWrap: {
      position: "absolute",
      top: 0,
      right: 0,
      bottom: 0,
      left: 0,
      alignItems: "center",
      justifyContent: "center",
      paddingHorizontal: Space.xs,
    },
    retry: {
      maxWidth: "100%",
      backgroundColor: C.elevated,
      ...shadowRaised(C),
    },
  });
}
