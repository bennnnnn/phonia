import { useMemo, type ReactNode } from "react";
import { StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { ActionFeedbackProvider } from "@/contexts/ActionFeedbackContext";
import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { FullScreenModal } from "@/ui/overlay/FullScreenModal";
import { HeaderButton } from "@/ui/controls/HeaderButton";

export type AttachmentViewerProps = {
  visible: boolean;
  onClose: () => void;
  fileName: string;
  onShare: () => void;
  /** The share is being prepared: the button spins and waits. */
  sharing?: boolean;
};

type Props = AttachmentViewerProps & {
  closeLabel: string;
  shareLabel: string;
  children: ReactNode;
};

/** The PDF and text viewers' page: close, the file name and Share above the file. */
export function AttachmentViewerChrome({
  visible,
  onClose,
  fileName,
  onShare,
  sharing = false,
  closeLabel,
  shareLabel,
  children,
}: Props) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const insets = useSafeAreaInsets();
  return (
    <FullScreenModal visible={visible} animationType="slide" onRequestClose={onClose}>
      {/* Toasts (a failed share) show inside the viewer, not under it. */}
      <ActionFeedbackProvider>
        <View style={[s.root, { paddingTop: insets.top, paddingBottom: insets.bottom }]}>
          <View style={s.toolbar}>
            <HeaderButton icon="close" onPress={onClose} accessibilityLabel={closeLabel} />
            <Text style={s.title} numberOfLines={1} ellipsizeMode="middle" accessibilityRole="header">
              {fileName}
            </Text>
            <HeaderButton icon="share" onPress={onShare} busy={sharing} accessibilityLabel={shareLabel} />
          </View>
          {children}
        </View>
      </ActionFeedbackProvider>
    </FullScreenModal>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    root: { flex: 1, backgroundColor: t.bg },
    toolbar: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.sm,
      paddingHorizontal: Space.md,
      paddingVertical: Space.sm,
      borderBottomWidth: 1,
      borderBottomColor: t.border,
    },
    title: { flex: 1, ...Type.body, ...Weight.semibold, color: t.text },
  });
}
