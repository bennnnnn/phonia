import { useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Image,
  Pressable,
  StyleSheet,
  Text,
  View,
  type ImageSourcePropType,
} from "react-native";

import { isShareCancelled } from "@/lib/shareCancelled";
import { tap } from "@/lib/haptics";
import { Radius } from "@/lib/radius";
import { presentShareSheet } from "@/lib/share";
import { Space } from "@/lib/space";
import { type Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";

import { IconButton } from "../controls/IconButton";
import { Icon } from "../icons/Icon";
import type { IconName } from "../icons/names";
import { IconSize } from "../icons/sizes";
import { useLiveAnnouncement } from "../hooks/useLiveAnnouncement";
import { Sheet } from "../overlay/Sheet";
import { useCopyText } from "./useCopyText";

const PREVIEW_ART = 44;
const ACTION = 56;

type Action = "share" | "copy" | "pdf";

type Props = {
  visible: boolean;
  onClose: () => void;
  /** "Share chat". */
  heading: string;
  /** One line on what is shared, e.g. "Shares a copy of this chat as it is now." */
  note?: string;
  preview: {
    title: string;
    /** Second line, e.g. "Recall · Sep 26". */
    meta?: string;
    /** App icon or thumbnail; an icon in a tinted circle otherwise. */
    image?: ImageSourcePropType;
    icon?: IconName;
  };
  /** The text Share and Copy hand over. Called once per opening. */
  load: () => Promise<string>;
  /** Title for the OS share menu (Mail subject on iOS). */
  shareTitle?: string;
  /** Adds a PDF button. Rejecting with a share cancel is not a failure. */
  onExportPdf?: () => Promise<void>;
  /** A failure's own words ("Nothing to export yet"), instead of `labels.failed`. */
  failureText?: (error: unknown) => string | null;
  labels: {
    share: string;
    copy: string;
    copied: string;
    pdf?: string;
    /** Spoken name of the card's copy button. */
    copyText: string;
    /** Shown under the buttons when an action fails. */
    failed: Record<Action, string>;
  };
  testID?: string;
};

/**
 * The share hub: a title, a preview card with a copy button, and round
 * Share / Copy / PDF buttons. The OS share menu opens on top right away;
 * the sheet stays underneath for Copy and PDF. It closes only when the
 * person closes it — dismissing it under the OS menu would take that menu
 * down too on iOS.
 */
export function ShareSheet({
  visible,
  onClose,
  heading,
  note,
  preview,
  load,
  shareTitle,
  onExportPdf,
  failureText,
  labels,
  testID = "share-sheet",
}: Props) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState<Action | null>(null);
  const { copied, copy: copyText, reset: resetCopied } = useCopyText();
  const [failed, setFailed] = useState<Action | null>(null);
  const [failedWords, setFailedWords] = useState<string | null>(null);
  useLiveAnnouncement(failed ? (failedWords ?? labels.failed[failed]) : null);
  const text = useRef<Promise<string> | null>(null);
  const loadRef = useRef(load);
  loadRef.current = load;
  const open = useRef(false);

  /** One load per opening; a failed load is tried again by the next action. */
  const getText = () => {
    if (!text.current) {
      const pending = loadRef.current();
      text.current = pending;
      pending.catch(() => {
        if (text.current === pending) text.current = null;
      });
    }
    return text.current;
  };

  const opening = useRef(0);
  useEffect(() => {
    open.current = visible;
    const id = ++opening.current;
    if (!visible) {
      text.current = null;
      return;
    }
    setReady(false);
    setBusy(null);
    resetCopied();
    setFailed(null);
    getText().then(
      () => {
        if (opening.current === id) setReady(true);
      },
      () => {
        if (opening.current !== id) return;
        setReady(true);
        setFailed("share");
      },
    );
  }, [visible, resetCopied]);

  const run = async (action: Action, work: () => Promise<void>) => {
    if (busy) return;
    setBusy(action);
    setFailed(null);
    try {
      await work();
    } catch (error) {
      if (open.current && !isShareCancelled(error)) {
        setFailedWords(failureText?.(error) ?? null);
        setFailed(action);
      }
    } finally {
      if (open.current) setBusy(null);
    }
  };

  const share = () =>
    run("share", async () => {
      const message = await getText();
      if (!open.current) return;
      await presentShareSheet({ message, title: shareTitle });
    });

  const copy = () =>
    run("copy", async () => {
      const message = await getText();
      if (!open.current) return;
      if (!(await copyText(message))) throw new Error("copy failed");
    });

  const exportPdf = () => {
    if (!onExportPdf) return;
    void run("pdf", onExportPdf);
  };

  const actions: { key: Action; icon: IconName; label: string; onPress: () => void }[] = [
    { key: "share", icon: "share", label: labels.share, onPress: () => void share() },
    {
      key: "copy",
      icon: copied ? "check" : "copy",
      label: copied ? labels.copied : labels.copy,
      onPress: () => void copy(),
    },
  ];
  if (onExportPdf && labels.pdf) {
    actions.push({ key: "pdf", icon: "file-text", label: labels.pdf, onPress: exportPdf });
  }

  return (
    <Sheet
      visible={visible}
      onClose={onClose}
      // Present the OS share menu on top as soon as the sheet is up.
      onShow={() => {
        void share();
      }}
      withHandle
      contentContainerStyle={s.panel}
    >
      <View style={s.body} testID={testID}>
        <Text style={s.heading} accessibilityRole="header">
          {heading}
        </Text>
        {note ? <Text style={s.note}>{note}</Text> : null}

        <View style={s.card}>
          {preview.image ? (
            <Image source={preview.image} style={s.art} accessibilityIgnoresInvertColors />
          ) : (
            <View style={[s.art, s.artIcon]}>
              <Icon name={preview.icon ?? "share"} size={IconSize.sm} color={theme.primary} />
            </View>
          )}
          <View style={s.cardCopy}>
            <Text style={s.cardTitle} numberOfLines={1}>
              {preview.title}
            </Text>
            {preview.meta ? (
              <Text style={s.cardMeta} numberOfLines={1}>
                {preview.meta}
              </Text>
            ) : null}
          </View>
          {ready ? (
            <IconButton
              name={copied ? "check" : "copy"}
              color={copied ? theme.success : theme.textSecondary}
              onPress={() => void copy()}
              accessibilityLabel={copied ? labels.copied : labels.copyText}
              testID={`${testID}-card-copy`}
            />
          ) : (
            <View style={s.cardSpinner}>
              <ActivityIndicator color={theme.textSecondary} />
            </View>
          )}
        </View>

        <View style={s.actions}>
          {actions.map((action) => (
            <Pressable
              key={action.key}
              onPress={() => {
                // Copy plays its own success haptic (useCopyText).
                if (action.key !== "copy") tap();
                action.onPress();
              }}
              disabled={busy != null}
              style={({ pressed }) => [s.action, pressed && s.actionPressed]}
              accessibilityRole="button"
              accessibilityLabel={action.label}
              accessibilityState={{ busy: busy === action.key, disabled: busy != null }}
              testID={`${testID}-${action.key}`}
            >
              <View style={[s.actionCircle, action.key === "copy" && copied && s.actionCircleDone]}>
                {busy === action.key && action.key !== "copy" ? (
                  <ActivityIndicator color={theme.text} />
                ) : (
                  <Icon
                    name={action.icon}
                    size={IconSize.md}
                    color={action.key === "copy" && copied ? theme.success : theme.text}
                  />
                )}
              </View>
              <Text style={s.actionLabel}>{action.label}</Text>
            </Pressable>
          ))}
        </View>

        {failed ? (
          <Text style={s.failed} accessibilityLiveRegion="polite" testID={`${testID}-failed`}>
            {failedWords ?? labels.failed[failed]}
          </Text>
        ) : null}
      </View>
    </Sheet>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    panel: { backgroundColor: t.elevated },
    body: {
      paddingHorizontal: Space.lg,
      paddingTop: Space.xs,
      paddingBottom: Space.md,
      gap: Space.md,
    },
    heading: { ...Type.title, ...Weight.semibold, color: t.text },
    note: { ...Type.secondary, color: t.textSecondary, marginTop: -Space.xs },
    card: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.sm,
      padding: Space.sm,
      paddingLeft: Space.md,
      borderRadius: Radius.card,
      backgroundColor: t.control,
    },
    art: {
      width: PREVIEW_ART,
      height: PREVIEW_ART,
      borderRadius: Radius.md,
    },
    artIcon: {
      backgroundColor: t.primaryLight,
      alignItems: "center",
      justifyContent: "center",
    },
    cardCopy: { flex: 1, minWidth: 0, gap: 2 },
    cardTitle: { ...Type.label, ...Weight.semibold, color: t.text },
    cardMeta: { ...Type.caption, color: t.textSecondary },
    cardSpinner: {
      width: Space.minTouch,
      height: Space.minTouch,
      alignItems: "center",
      justifyContent: "center",
    },
    actions: {
      flexDirection: "row",
      justifyContent: "center",
      gap: Space.xl,
      paddingTop: Space.xs,
    },
    action: { alignItems: "center", gap: Space.xs, minWidth: ACTION + Space.xs },
    actionPressed: { opacity: 0.7 },
    actionCircle: {
      width: ACTION,
      height: ACTION,
      borderRadius: ACTION / 2,
      backgroundColor: t.control,
      alignItems: "center",
      justifyContent: "center",
    },
    actionCircleDone: { backgroundColor: t.successLight },
    actionLabel: { ...Type.caption, color: t.textSecondary },
    failed: { ...Type.caption, color: t.danger, textAlign: "center" },
  });
}
