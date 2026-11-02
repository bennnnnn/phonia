/**
 * The waiting card after a tap: a coarser grid with a short snake of accent
 * dots walking toward a food dot (rules in `model/dotSnake.ts`). Each step is
 * a React render of a dozen SVG circles every DOT_SNAKE_STEP_MS, which is
 * cheap and works in every build.
 *
 * Renders the drawing (an image for screen readers) and, beside it, the full
 * card touch surface: a tap steers toward that spot, a long press stops.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { type GestureResponderEvent, Pressable, StyleSheet, View } from "react-native";
import Svg, { Circle } from "react-native-svg";
import { useTranslation } from "react-i18next";

import {
  type Cell,
  cellAtPoint,
  cellCenter,
  type DotGrid,
  dotGridLayout,
} from "@/features/images/model/dotGrid";
import {
  createDotSnake,
  directionVector,
  DOT_SNAKE_STEP_MS,
  type DotSnake,
  steerDotSnake,
  stepDotSnake,
} from "@/features/images/model/dotSnake";
import { selection } from "@/lib/haptics";
import { withAlpha } from "@/lib/theme";

import { DotGridPattern } from "./DotGridSvg";
import { type DotFieldPalette, PLAY_GRID_DOT_RADIUS, playPitch } from "./dotField";

type Props = {
  width: number;
  height: number;
  palette: DotFieldPalette;
  /** The card's fill; laid under each snake dot so the grid dot beneath does not show through. */
  cardColor: string;
  /** Ink for the head's eyes (on the accent). */
  eyeColor: string;
  /** What the image is: the stage line and progress. */
  accessibilityLabel: string;
  onStop: () => void;
};

/** Head is the biggest and strongest dot; the tail fades and shrinks. */
const HEAD_RADIUS = 0.32;
const TAIL_RADIUS = 0.2;
const FOOD_RADIUS = 0.27;
const TAIL_OPACITY = 0.5;

type Dot = { key: string; cell: Cell; radius: number; opacity: number };

export function DotSnakePlay({
  width,
  height,
  palette,
  cardColor,
  eyeColor,
  accessibilityLabel,
  onStop,
}: Props) {
  const { t } = useTranslation();
  const grid = useMemo(() => dotGridLayout(width, height, playPitch(width)), [width, height]);
  const [snake, setSnake] = useState<DotSnake>(() => createDotSnake(grid.cols, grid.rows));

  useEffect(() => {
    const id = setInterval(() => {
      setSnake((current) =>
        current.cols === grid.cols && current.rows === grid.rows
          ? stepDotSnake(current)
          : createDotSnake(grid.cols, grid.rows),
      );
    }, DOT_SNAKE_STEP_MS);
    return () => clearInterval(id);
  }, [grid.cols, grid.rows]);

  const steer = useCallback(
    (event: GestureResponderEvent) => {
      const { locationX, locationY } = event.nativeEvent;
      selection();
      setSnake((current) => steerDotSnake(current, cellAtPoint(grid, locationX, locationY)));
    },
    [grid],
  );

  const { pitch } = grid;
  const count = snake.body.length;
  const dots: Dot[] = snake.body.map((cell, index) => {
    const share = count > 1 ? index / (count - 1) : 0;
    return {
      key: `s${index}`,
      cell,
      radius: pitch * (HEAD_RADIUS + (TAIL_RADIUS - HEAD_RADIUS) * share),
      opacity: palette.accent.opacity * (1 - (1 - TAIL_OPACITY) * share),
    };
  });
  if (snake.food) {
    dots.push({
      key: "food",
      cell: snake.food,
      radius: pitch * FOOD_RADIUS,
      opacity: palette.accent.opacity,
    });
  }
  const head = snake.body[0];
  const headCenter = head ? cellCenter(grid, head) : null;
  const headRadius = pitch * HEAD_RADIUS;
  const look = directionVector(snake.direction);

  return (
    <>
      <View
        style={StyleSheet.absoluteFill}
        accessible
        accessibilityRole="image"
        accessibilityLabel={accessibilityLabel}
        testID="image-gen-dots-play"
      >
        <Svg width={width} height={height}>
          <DotGridPattern
            grid={grid}
            radius={PLAY_GRID_DOT_RADIUS}
            fill={withAlpha(palette.playGrid.color, palette.playGrid.opacity)}
          />
          {dots.map((dot) => (
            <Circle
              key={`under-${dot.key}`}
              {...centerProps(grid, dot.cell)}
              r={dot.radius}
              fill={cardColor}
            />
          ))}
          {dots.map((dot) => (
            <Circle
              key={dot.key}
              {...centerProps(grid, dot.cell)}
              r={dot.radius}
              fill={withAlpha(palette.accent.color, dot.opacity)}
            />
          ))}
          {headCenter
            ? [-1, 1].map((side) => (
                <Circle
                  key={`eye${side}`}
                  cx={headCenter.x + look.x * headRadius * 0.3 - look.y * side * headRadius * 0.4}
                  cy={headCenter.y + look.y * headRadius * 0.3 + look.x * side * headRadius * 0.4}
                  r={headRadius * 0.16}
                  fill={eyeColor}
                />
              ))
            : null}
        </Svg>
      </View>
      <Pressable
        style={StyleSheet.absoluteFill}
        onPress={steer}
        onLongPress={onStop}
        delayLongPress={450}
        accessibilityRole="button"
        accessibilityLabel={t("chat.image_gen_play")}
        accessibilityHint={t("chat.image_gen_steer_hint")}
        accessibilityState={{ selected: true }}
        testID="image-gen-play-surface"
      />
    </>
  );
}

function centerProps(grid: DotGrid, cell: Cell) {
  const { x, y } = cellCenter(grid, cell);
  return { cx: x, cy: y };
}
