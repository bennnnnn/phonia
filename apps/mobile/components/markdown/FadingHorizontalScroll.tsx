/**
 * A sideways ScrollView that shows where it is cut: a soft fade over each
 * clipped edge (the right one until the end is reached, the left one once
 * scrolled). The fade is the screen background, so it reads in light and
 * dark. iOS keeps no scrollbar on screen, so the indicator also flashes once
 * when the content first overflows.
 */
import { ReactNode, useRef, useState } from "react";
import {
  ScrollView,
  StyleSheet,
  View,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  type StyleProp,
  type ViewStyle,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";

import { useTheme, withAlpha } from "@/lib/theme";

const SCROLL_FADE_WIDTH = 28;
/** Offsets this close to an edge count as being at it (sub-pixel rounding). */
const EDGE_SLOP = 2;

/** Whether content is hidden past each edge at this offset. */
export function hiddenScrollEdges(offset: number, viewport: number, content: number) {
  return {
    start: offset > EDGE_SLOP,
    end: content - (offset + viewport) > EDGE_SLOP,
  };
}

type Props = {
  testID?: string;
  /** Width of what scrolls, and of the window it scrolls in. */
  contentWidth: number;
  viewportWidth: number;
  style?: StyleProp<ViewStyle>;
  children: ReactNode;
};

export function FadingHorizontalScroll({
  testID,
  contentWidth,
  viewportWidth,
  style,
  children,
}: Props) {
  const theme = useTheme();
  const scrollRef = useRef<ScrollView>(null);
  const flashed = useRef(false);
  const scrollable = contentWidth > viewportWidth + 1;
  const [offset, setOffset] = useState(0);
  const hidden = hiddenScrollEdges(offset, viewportWidth, contentWidth);
  const clear = withAlpha(theme.bg, 0);
  const solid = withAlpha(theme.bg, 0.9);

  const onScroll = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    const x = Math.max(0, e.nativeEvent.contentOffset.x);
    // Only an edge change re-renders the table, not every scrolled pixel.
    const next = hiddenScrollEdges(x, viewportWidth, contentWidth);
    if (next.start !== hidden.start || next.end !== hidden.end) setOffset(x);
  };

  return (
    <View style={[s.frame, style]}>
      <ScrollView
        ref={scrollRef}
        testID={testID}
        horizontal
        nestedScrollEnabled
        directionalLockEnabled
        bounces={false}
        overScrollMode="never"
        showsHorizontalScrollIndicator={scrollable}
        persistentScrollbar={scrollable}
        scrollEnabled={scrollable}
        scrollEventThrottle={32}
        onScroll={scrollable ? onScroll : undefined}
        onContentSizeChange={() => {
          if (!scrollable || flashed.current) return;
          flashed.current = true;
          scrollRef.current?.flashScrollIndicators?.();
        }}
        style={s.scroll}
        contentContainerStyle={scrollable ? { width: contentWidth } : undefined}
      >
        {children}
      </ScrollView>
      {scrollable && hidden.start ? (
        <LinearGradient
          testID="scroll-fade-start"
          colors={[solid, clear]}
          start={{ x: 0, y: 0.5 }}
          end={{ x: 1, y: 0.5 }}
          style={[s.fade, s.fadeStart]}
          pointerEvents="none"
        />
      ) : null}
      {scrollable && hidden.end ? (
        <LinearGradient
          testID="scroll-fade-end"
          colors={[clear, solid]}
          start={{ x: 0, y: 0.5 }}
          end={{ x: 1, y: 0.5 }}
          style={[s.fade, s.fadeEnd]}
          pointerEvents="none"
        />
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  frame: { position: "relative", minWidth: 0 },
  scroll: {
    backgroundColor: "transparent",
    width: "100%",
    maxWidth: "100%",
    minWidth: 0,
  },
  fade: { position: "absolute", top: 0, bottom: 0, width: SCROLL_FADE_WIDTH },
  fadeStart: { left: 0 },
  fadeEnd: { right: 0 },
});
