import { type ReactNode } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Space } from "@/lib/space";

/** Cap auth columns on tablet so login/onboarding don't stretch edge-to-edge. */
export const AUTH_COLUMN_MAX_WIDTH = 420;

type Props = {
  children: ReactNode;
  /** How to distribute hero vs actions when the column is taller than content. */
  justify?: "space-between" | "center";
};

/**
 * Scroll + keyboard-safe column for login and onboarding. `flexGrow: 1` keeps
 * short content filling the screen; small/landscape devices can still scroll.
 */
export function AuthScrollLayout({
  children,
  justify = "space-between",
}: Props) {
  const insets = useSafeAreaInsets();

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
        contentContainerStyle={[
          styles.scroll,
          {
            paddingTop: Math.max(insets.top, Space.md),
            paddingBottom: Math.max(insets.bottom, Space.md),
          },
        ]}
        testID="auth-scroll-layout"
      >
        <View style={[styles.column, { justifyContent: justify }]}>{children}</View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  scroll: {
    flexGrow: 1,
    paddingHorizontal: Space.lg,
  },
  column: {
    flexGrow: 1,
    width: "100%",
    maxWidth: AUTH_COLUMN_MAX_WIDTH,
    alignSelf: "center",
  },
});
