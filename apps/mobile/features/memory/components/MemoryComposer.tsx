import { useMemo, useRef, useState } from "react";
import { ActivityIndicator, Platform, Pressable, StyleSheet, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTranslation } from "react-i18next";

import { tap } from "@/lib/haptics";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { type Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";
import { useKeyboardHeight } from "@/ui/hooks/useKeyboardHeight";
import { Icon } from "@/ui/icons/Icon";
import { IconSize } from "@/ui/icons/sizes";

/** Same limit as the server (MEMORY_INSTRUCTION_MAX_LENGTH). */
const MEMORY_INSTRUCTION_MAX_LENGTH = 500;

type Props = {
  /** An example instruction, e.g. "Keep lists under five things". */
  placeholder: string;
  /** Resolves true when memory took the edit; the box then clears. */
  onSubmit: (instruction: string) => Promise<boolean>;
};

/**
 * "Tell Recall what to change": a plain-words edit box docked under the memory
 * pages. On iOS it rides above the keyboard; Android resizes the window itself.
 */
export function MemoryComposer({ placeholder, onSubmit }: Props) {
  const theme = useTheme();
  const { t } = useTranslation();
  const insets = useSafeAreaInsets();
  const keyboard = useKeyboardHeight(Platform.OS === "ios");
  const s = useMemo(() => makeStyles(theme), [theme]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const ready = text.trim().length > 0 && !busy;

  const send = async () => {
    const instruction = text.trim();
    if (!instruction || busyRef.current) return;
    tap();
    busyRef.current = true;
    setBusy(true);
    const ok = await onSubmit(instruction);
    busyRef.current = false;
    setBusy(false);
    if (ok) setText("");
  };

  return (
    <View style={[s.bar, { paddingBottom: (keyboard > 0 ? keyboard : insets.bottom) + Space.xs }]}>
      <View style={s.field}>
        <TextInput
          style={s.input}
          value={text}
          onChangeText={setText}
          placeholder={placeholder}
          placeholderTextColor={theme.textTertiary}
          multiline
          maxLength={MEMORY_INSTRUCTION_MAX_LENGTH}
          editable={!busy}
          accessibilityLabel={t("memory.composer_label")}
          accessibilityHint={placeholder}
          testID="memory-composer-input"
        />
        <Pressable
          style={[s.send, !ready && s.sendIdle]}
          onPress={() => void send()}
          disabled={!ready}
          hitSlop={Space.xxs}
          accessibilityRole="button"
          accessibilityLabel={t("memory.composer_send")}
          accessibilityState={{ disabled: !ready, busy }}
          testID="memory-composer-send"
        >
          {busy ? (
            <ActivityIndicator size="small" color={theme.textTertiary} />
          ) : (
            <Icon name="arrow-up" size={IconSize.sm} color={ready ? theme.onPrimary : theme.textTertiary} />
          )}
        </Pressable>
      </View>
    </View>
  );
}

const SEND_SIZE = Space.xl + Space.xxs;

function makeStyles(t: Theme) {
  return StyleSheet.create({
    bar: {
      paddingHorizontal: Space.md,
      paddingTop: Space.xs,
      backgroundColor: t.bg,
    },
    field: {
      flexDirection: "row",
      alignItems: "flex-end",
      gap: Space.xs,
      minHeight: Space.xl + Space.gutter,
      paddingLeft: Space.md,
      paddingRight: Space.xs,
      paddingVertical: Space.xs,
      borderRadius: Radius.composer,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: t.border,
      backgroundColor: t.surface,
    },
    input: {
      flex: 1,
      ...Type.body,
      color: t.text,
      maxHeight: Space.xl * 4,
      paddingVertical: Space.xs,
    },
    send: {
      width: SEND_SIZE,
      height: SEND_SIZE,
      borderRadius: Radius.full,
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: t.primary,
    },
    sendIdle: { backgroundColor: t.control },
  });
}
