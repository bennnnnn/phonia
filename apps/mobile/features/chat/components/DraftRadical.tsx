import { useState, type ReactNode } from "react";
import { StyleSheet, View } from "react-native";
import Svg, { Path } from "react-native-svg";

import { radicalStroke, type MathLayout } from "@/lib/math/layout";

const EM = 16;
const INDEX_FONT = 12;

function radicalLayout(contentWidth: number, contentHeight: number, hasIndex: boolean): MathLayout {
  const lead = Math.max(EM * 0.72, hasIndex ? EM * 0.9 : EM * 0.62);
  const barStart = lead;
  const barEnd = barStart + Math.max(contentWidth, EM * 0.45) + EM * 0.1;
  const height = Math.max(EM * 1.35, contentHeight + EM * 0.2);
  return {
    kind: "sqrt",
    width: barEnd,
    height,
    outer: 0,
    inkWidth: contentWidth,
    children: [],
    em: EM,
    barStart,
    barEnd,
    index: hasIndex
      ? { left: 1, top: EM * 0.02, width: EM * 0.7, fontSize: INDEX_FONT, lineHeight: INDEX_FONT }
      : undefined,
  };
}

/** One stroke for the hook and the bar, matching the message radical. */
export function DraftRadical({
  color,
  index,
  children,
}: {
  color: string;
  index?: ReactNode;
  children: ReactNode;
}) {
  const [box, setBox] = useState({ width: 14, height: 18 });
  const layout = radicalLayout(box.width, box.height, index != null);
  const stroke = radicalStroke(layout);
  const bodyLeft = layout.barStart ?? 0;
  const bodyTop = EM * 0.08;
  return (
    <View style={{ width: layout.width, height: layout.height }} testID="math-sqrt">
      <Svg
        testID="math-radical-glyph"
        width={layout.width}
        height={layout.height}
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        style={StyleSheet.absoluteFill}
        pointerEvents="none"
      >
        <Path
          d={stroke.d}
          fill="none"
          stroke={color}
          strokeWidth={Math.max(1.1, EM * 0.075)}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </Svg>
      {index && layout.index ? (
        <View style={[styles.index, { left: layout.index.left, top: layout.index.top }]}>{index}</View>
      ) : null}
      <View
        testID="math-sqrt-radicand"
        style={[styles.body, { left: bodyLeft, top: bodyTop }]}
        onLayout={(event) => {
          const width = Math.ceil(event.nativeEvent.layout.width);
          const height = Math.ceil(event.nativeEvent.layout.height);
          setBox((prev) => (prev.width === width && prev.height === height ? prev : { width, height }));
        }}
      >
        {children}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  index: {
    position: "absolute",
  },
  body: {
    position: "absolute",
  },
});
