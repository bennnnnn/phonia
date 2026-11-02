import { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Image,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  View,
} from "react-native";
import type { EdgeInsets } from "react-native-safe-area-context";
import { useTranslation } from "react-i18next";

import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";
import { Button } from "@/ui/controls/Button";
import { TextField } from "@/ui/controls/TextField";
import { useLiveAnnouncement } from "@/ui/hooks/useLiveAnnouncement";

export type ScanReadingState =
  | { status: "reading" }
  | { status: "ready"; reading: string; uncertain: boolean }
  | { status: "failed"; message?: string };

type Props = {
  photoUri: string;
  state: ScanReadingState;
  insets: EdgeInsets;
  /** Solve the confirmed (possibly edited) text as a typed message. */
  onSolve: (reading: string) => void;
  /** Send the photo itself; carries the reading when the student saw one. */
  onSendPhoto: (reading: string) => void;
  onRetake: () => void;
};

/**
 * "I read this as" between the crop and the chat: the student checks the
 * reading, fixes a misread digit, then solves the text. Sending the photo
 * never waits on the read, so the scanner still closes at once for anyone
 * who does not want to check.
 */
export function ScanReadingReview({
  photoUri,
  state,
  insets,
  onSolve,
  onSendPhoto,
  onRetake,
}: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const [draft, setDraft] = useState("");

  const readingText = state.status === "ready" ? state.reading : "";
  useLiveAnnouncement(state.status === "failed" ? (state.message ?? t("chat.math_scan_read_failed")) : null);
  useEffect(() => {
    setDraft(readingText);
  }, [readingText]);

  const canSolve = state.status === "ready" && draft.trim().length > 0;
  // An emptied ready reading must not go out as "no reading": the parent
  // treats "" as no confirmation and the server reads the photo again.
  const canSendPhoto = state.status !== "ready" || draft.trim().length > 0;

  return (
    <KeyboardAvoidingView
      style={[StyleSheet.absoluteFill, s.layer]}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      testID="math-scan-review"
    >
      <View style={[s.photoArea, { paddingTop: insets.top + Space.md }]}>
        <Image
          source={{ uri: photoUri }}
          style={s.photo}
          resizeMode="contain"
          accessibilityIgnoresInvertColors
        />
      </View>
      <View style={[s.card, { paddingBottom: insets.bottom + Space.md }]}>
        {state.status === "reading" ? (
          <View style={s.readingRow} accessibilityLiveRegion="polite">
            <ActivityIndicator color={theme.textSecondary} />
            <Text style={s.note}>{t("chat.math_scan_reading")}</Text>
          </View>
        ) : null}
        {state.status === "failed" ? (
          <Text style={s.note} accessibilityLiveRegion="polite">
            {state.message ?? t("chat.math_scan_read_failed")}
          </Text>
        ) : null}
        {state.status === "ready" ? (
          <TextField
            label={t("chat.math_scan_read_as")}
            value={draft}
            onChangeText={setDraft}
            multiline
            autoCapitalize="none"
            autoCorrect={false}
            spellCheck={false}
            helper={state.uncertain ? t("chat.math_scan_uncertain") : undefined}
            testID="math-scan-reading"
          />
        ) : null}
        <View style={s.actions}>
          <Button
            title={t("chat.math_scan_solve")}
            onPress={() => onSolve(draft.trim())}
            disabled={!canSolve}
            size="lg"
            style={s.fill}
          />
          <View style={s.secondary}>
            <Button
              title={t("chat.math_scan_retake")}
              onPress={onRetake}
              variant="ghost"
              style={s.fill}
            />
            <Button
              title={t("chat.math_scan_send_photo")}
              onPress={() => {
                if (!canSendPhoto) return;
                onSendPhoto(state.status === "ready" ? draft.trim() : "");
              }}
              disabled={!canSendPhoto}
              variant="outline"
              style={s.fill}
            />
          </View>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    layer: {
      zIndex: 50,
    },
    photoArea: {
      flex: 1,
      paddingHorizontal: Space.gutter,
      paddingBottom: Space.md,
      backgroundColor: theme.mediaScrim,
    },
    photo: {
      flex: 1,
    },
    card: {
      backgroundColor: theme.elevated,
      borderTopLeftRadius: Radius.sheet,
      borderTopRightRadius: Radius.sheet,
      paddingTop: Space.gutter,
      paddingHorizontal: Space.gutter,
      gap: Space.md,
    },
    readingRow: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.sm,
      minHeight: 44,
    },
    note: {
      ...Type.body,
      color: theme.textSecondary,
    },
    actions: {
      gap: Space.sm,
    },
    secondary: {
      flexDirection: "row",
      gap: Space.sm,
    },
    fill: {
      flex: 1,
    },
  });
}
