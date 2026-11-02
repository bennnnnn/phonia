/**
 * Full-screen rotate surface for a 3D molecule. The inline card stays the
 * entry point; this layer owns the drag so the chat list cannot steal it.
 */
import { useMemo, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { StyleSheet, View } from "react-native";
import { Gesture, GestureDetector, GestureHandlerRootView } from "react-native-gesture-handler";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { useTheme } from "@/lib/theme";
import { HeaderButton } from "@/ui/controls/HeaderButton";
import { FullScreenModal } from "@/ui/overlay/FullScreenModal";

type Size = { width: number; height: number };

type Props = {
  visible: boolean;
  onClose: () => void;
  onGrant: () => void;
  onMove: (translationX: number, translationY: number) => void;
  children: (size: Size) => ReactNode;
};

export function MoleculeRotateModal({ visible, onClose, onGrant, onMove, children }: Props) {
  const theme = useTheme();
  const { t } = useTranslation();
  const insets = useSafeAreaInsets();
  const s = useMemo(() => makeStyles(), []);
  const [size, setSize] = useState<Size>({ width: 0, height: 0 });
  const grantRef = useRef(onGrant);
  const moveRef = useRef(onMove);
  grantRef.current = onGrant;
  moveRef.current = onMove;

  const gesture = useMemo(
    () =>
      Gesture.Pan()
        .runOnJS(true)
        .onBegin(() => {
          grantRef.current();
        })
        .onUpdate((event) => {
          moveRef.current(event.translationX, event.translationY);
        }),
    [],
  );

  return (
    <FullScreenModal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      {visible ? (
        <GestureHandlerRootView
          style={[s.root, { backgroundColor: theme.scrim }]}
          testID="molecule-rotate-layer"
        >
          <View
            style={[
              s.sheet,
              {
                backgroundColor: theme.elevated,
                marginTop: Math.max(insets.top, Space.sm),
                paddingBottom: insets.bottom,
                borderColor: theme.border,
              },
            ]}
          >
            <View style={s.toolbar}>
              <HeaderButton
                icon="close"
                onPress={onClose}
                testID="molecule-rotate-close"
                accessibilityLabel={t("preview.close")}
              />
            </View>
            <GestureDetector gesture={gesture}>
              <View
                collapsable={false}
                style={s.stage}
                testID="molecule-rotate-surface"
                onLayout={(event) => {
                  const { width, height } = event.nativeEvent.layout;
                  if (width > 0 && height > 0) setSize({ width, height });
                }}
              >
                {size.width > 0 ? children(size) : null}
              </View>
            </GestureDetector>
          </View>
        </GestureHandlerRootView>
      ) : null}
    </FullScreenModal>
  );
}

function makeStyles() {
  return StyleSheet.create({
    root: { flex: 1 },
    sheet: {
      flex: 1,
      borderTopLeftRadius: Radius.sheet,
      borderTopRightRadius: Radius.sheet,
      borderTopWidth: StyleSheet.hairlineWidth,
      overflow: "hidden",
    },
    toolbar: {
      alignItems: "flex-end",
      paddingHorizontal: Space.sm,
      paddingTop: Space.xs,
    },
    stage: { flex: 1 },
  });
}
