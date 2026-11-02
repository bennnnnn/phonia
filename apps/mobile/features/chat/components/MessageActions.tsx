/** The action rows under a chat message: copy for a sent one; copy, read aloud, thumbs and regenerate for a reply. */
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ActivityIndicator, Pressable, StyleSheet, View } from "react-native";
import { useTranslation } from "react-i18next";

import { useAuthToken, useAuthUserReader } from "@/contexts/AuthContext";
import { useActionFeedbackOptional } from "@/contexts/actionFeedbackCore";
import { readAloudIsCut, speakPlainText, stopSpeaking } from "@/features/speech/model/pronunciation";
import { extractPrimaryCopyText } from "@/lib/copyBlock";
import { notifySuccess, notifyWarning, tap } from "@/lib/haptics";
import { speechLocale } from "@/lib/i18n/languages";
import { hasPlanFeature } from "@/lib/plan";
import { reportRecoverableError } from "@/lib/reportRecoverableError";
import { Space } from "@/lib/space";
import type { Theme } from "@/lib/theme";
import { Icon } from "@/ui/icons/Icon";
import { IconSize } from "@/ui/icons/sizes";
import { useCopyText } from "@/ui/share/useCopyText";

/** Each action's touch target (the platform minimum). */
const ACTION_SIZE = 44;

type Feedback = "up" | "down" | null;

/** Copy `text` and show the check; a refused copy says so. */
function useCopyAction(text: string) {
  const { t } = useTranslation();
  const feedback = useActionFeedbackOptional();
  const { copied, copy } = useCopyText(() =>
    reportRecoverableError(feedback, t("share.copy_failed")),
  );
  return { copied, copy: () => copy(text) };
}

function ActionButton({
  label,
  onPress,
  disabled,
  busy,
  selected,
  children,
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  /** Regenerate's spinner: announced as disabled and busy. */
  busy?: boolean;
  /** A toggle drawn filled while on (a rating, read aloud): announced as selected. */
  selected?: boolean;
  children: ReactNode;
}) {
  return (
    <Pressable
      style={a.btn}
      onPress={onPress}
      hitSlop={8}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={
        busy == null && selected == null ? undefined : { selected, ...(busy == null ? null : { disabled: busy, busy }) }
      }
    >
      {children}
    </Pressable>
  );
}

function CopyButton({ copied, onPress, disabled, theme }: {
  copied: boolean;
  onPress: () => void;
  disabled: boolean;
  theme: Theme;
}) {
  const { t } = useTranslation();
  return (
    <ActionButton label={t("common.copy")} onPress={onPress} disabled={disabled}>
      <Icon
        name={copied ? "check" : "copy"}
        size={IconSize.sm}
        color={copied ? theme.primary : theme.textSecondary}
      />
    </ActionButton>
  );
}

export function UserActions({
  content,
  theme,
}: {
  content: string;
  theme: Theme;
}) {
  const { copied, copy } = useCopyAction(content);
  return (
    <View style={a.userRow}>
      <CopyButton
        copied={copied}
        onPress={() => void copy()}
        disabled={!content.trim()}
        theme={theme}
      />
    </View>
  );
}

/**
 * Read a reply aloud, with a Stop that belongs to that reply. Keyed by reply:
 * a list row reused for another reply must not show (or act as) the Stop of
 * the one it showed before.
 */
function useReadAloud(messageId: string, markdown: string) {
  const { t } = useTranslation();
  // Read on press, not subscribed: a profile or quota patch must not re-render every reply's row.
  const readUser = useAuthUserReader();
  const token = useAuthToken();
  const feedbackApi = useActionFeedbackOptional();
  const [speakingId, setSpeakingId] = useState<string | null>(null);
  const speaking = speakingId === messageId;
  const speakGenRef = useRef(0);
  const readingRef = useRef(false);

  // Stop lives on this reply. When the reply leaves (another chat, a
  // regenerate, or the list reusing the row), stop its reading with it;
  // otherwise the voice keeps fetching and reading with no way to stop it.
  useEffect(
    () => () => {
      if (!readingRef.current) return;
      readingRef.current = false;
      speakGenRef.current += 1;
      stopSpeaking();
      setSpeakingId(null);
    },
    [messageId],
  );

  const toggleSpeaking = async () => {
    if (speaking) {
      speakGenRef.current += 1;
      readingRef.current = false;
      stopSpeaking();
      setSpeakingId(null);
      return;
    }
    const gen = ++speakGenRef.current;
    tap();
    readingRef.current = true;
    setSpeakingId(messageId);
    // The natural (cloud) voice is a paid feature the server enforces; other
    // plans read with the phone's own voice, which never reaches the server.
    const user = readUser();
    const cloudVoice = hasPlanFeature(user, "speech_tts");
    if (readAloudIsCut(markdown)) feedbackApi?.info(t("chat.read_aloud_cut"));
    const result = await speakPlainText(markdown, speechLocale(user?.locale), {
      token: cloudVoice ? token : null,
      preferCloud: cloudVoice,
    });
    if (gen !== speakGenRef.current) return;
    readingRef.current = false;
    setSpeakingId(null);
    if (!result.ok) {
      reportRecoverableError(
        feedbackApi,
        result.reason === "unavailable"
          ? t("chat.read_aloud_unavailable_body")
          : t("chat.read_aloud_failed_body"),
      );
    }
  };

  return { speaking, toggleSpeaking };
}

export function AssistantActions({
  messageId,
  markdown,
  feedback,
  onFeedback,
  onRegenerate,
  regenerating = false,
  theme,
  thumbsOnly = false,
}: {
  messageId: string;
  markdown: string;
  feedback: Feedback;
  onFeedback?: (messageId: string, feedback: Feedback) => void;
  onRegenerate?: () => void;
  regenerating?: boolean;
  theme: Theme;
  /** Image-only replies: thumbs only (no copy / speak / regenerate). */
  thumbsOnly?: boolean;
}) {
  const { t } = useTranslation();
  const copyPayload = extractPrimaryCopyText(markdown);
  const { copied, copy } = useCopyAction(copyPayload);
  const { speaking, toggleSpeaking } = useReadAloud(messageId, markdown);

  const rate = (dir: "up" | "down") => {
    const next = feedback === dir ? null : dir;
    onFeedback?.(messageId, next);
    if (next === "up") notifySuccess();
    else if (next === "down") notifyWarning();
    else tap();
  };

  return (
    <View style={a.row}>
      {!thumbsOnly ? (
        <>
          <CopyButton
            copied={copied}
            onPress={copy}
            disabled={!copyPayload.trim()}
            theme={theme}
          />
          <ActionButton
            label={t("chat.read_aloud_a11y")}
            onPress={() => void toggleSpeaking()}
            disabled={!markdown.trim()}
            selected={speaking}
          >
            <Icon
              name="volume"
              filled={speaking}
              size={IconSize.sm}
              color={speaking ? theme.primary : theme.textSecondary}
            />
          </ActionButton>
        </>
      ) : null}
      <ActionButton label={t("chat.thumbs_up_a11y")} onPress={() => rate("up")} selected={feedback === "up"}>
        <Icon
          name="thumbs-up"
          filled={feedback === "up"}
          size={IconSize.sm}
          color={feedback === "up" ? theme.primary : theme.textSecondary}
        />
      </ActionButton>
      <ActionButton label={t("chat.thumbs_down_a11y")} onPress={() => rate("down")} selected={feedback === "down"}>
        <Icon
          name="thumbs-down"
          filled={feedback === "down"}
          size={IconSize.sm}
          color={feedback === "down" ? theme.danger : theme.textSecondary}
        />
      </ActionButton>
      {!thumbsOnly && onRegenerate ? (
        <ActionButton
          label={t("chat.regenerate_a11y")}
          onPress={() => {
            tap();
            onRegenerate();
          }}
          disabled={regenerating}
          busy={regenerating}
        >
          {regenerating ? (
            <ActivityIndicator size="small" color={theme.primary} />
          ) : (
            <Icon name="refresh" size={IconSize.sm} color={theme.textSecondary} />
          )}
        </ActionButton>
      ) : null}
    </View>
  );
}

/** The minimum height of the slot an assistant's action row sits in. */
export const MESSAGE_ACTION_ROW_HEIGHT = ACTION_SIZE;

const a = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 2,
    marginTop: Space.xxs,
    marginLeft: 2,
  },
  userRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "flex-end",
    gap: 2,
    marginTop: Space.xxs,
    marginRight: 2,
  },
  btn: {
    width: ACTION_SIZE,
    height: ACTION_SIZE,
    alignItems: "center",
    justifyContent: "center",
  },
});
