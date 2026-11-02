import {
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PropsWithChildren,
} from "react";
import { StyleSheet, View } from "react-native";

import { ActionBanner, type ActionBannerAppearance } from "@/ui/feedback/ActionBanner";
import {
  ActionFeedbackContext,
  type ActionFeedbackApi,
  type ActionFeedbackOptions,
  type ActionFeedbackTone,
} from "@/contexts/actionFeedbackCore";
import { notifyError, notifySuccess, notifyWarning } from "@/lib/haptics";
import type { IconName } from "@/ui/icons/names";

type FeedbackItem = {
  id: number;
  message: string;
  tone: ActionFeedbackTone;
  icon: IconName;
};

const DEFAULT_ICONS: Record<ActionFeedbackTone, IconName> = {
  success: "check-circle-filled",
  info: "info",
  warning: "warning",
  error: "alert-circle",
};

/**
 * Owns the toast. The app root mounts one; a full-screen modal (photo, PDF or
 * text viewer) mounts its own inside the modal, and while it is mounted every
 * toast, from the modal or the screen under it, shows there.
 */
export function ActionFeedbackProvider({
  children,
  appearance = "default",
}: PropsWithChildren<{ appearance?: ActionBannerAppearance }>) {
  const parent = useContext(ActionFeedbackContext);
  const nextId = useRef(0);
  const overlays = useRef<ActionFeedbackApi[]>([]);
  const [item, setItem] = useState<FeedbackItem | null>(null);

  const dismissHere = useCallback(() => setItem(null), []);
  const showHere = useCallback((message: string, options: ActionFeedbackOptions = {}) => {
    const tone = options.tone ?? "success";
    nextId.current += 1;
    setItem({
      id: nextId.current,
      message,
      tone,
      icon: options.icon ?? DEFAULT_ICONS[tone],
    });
    if (options.haptic === false || tone === "info") return;
    if (tone === "success") notifySuccess();
    else if (tone === "error") notifyError();
    else notifyWarning();
  }, []);

  const show = useCallback((message: string, options: ActionFeedbackOptions = {}) => {
    const overlay = overlays.current[overlays.current.length - 1];
    if (overlay) overlay.show(message, options);
    else showHere(message, options);
  }, [showHere]);

  const dismiss = useCallback(() => {
    const overlay = overlays.current[overlays.current.length - 1];
    if (overlay) overlay.dismiss();
    else dismissHere();
  }, [dismissHere]);

  const capture = useCallback((overlay: ActionFeedbackApi) => {
    overlays.current = [...overlays.current, overlay];
    return () => {
      overlays.current = overlays.current.filter((entry) => entry !== overlay);
    };
  }, []);

  const api = useMemo<ActionFeedbackApi>(
    () => ({
      show,
      success: (message, options) => show(message, { ...options, tone: "success" }),
      info: (message, options) => show(message, { ...options, tone: "info" }),
      warning: (message, options) => show(message, { ...options, tone: "warning" }),
      error: (message, options) => show(message, { ...options, tone: "error" }),
      dismiss,
      capture,
    }),
    [capture, dismiss, show],
  );

  useEffect(() => parent?.capture?.(api), [parent, api]);

  return (
    <ActionFeedbackContext.Provider value={api}>
      <View style={styles.host}>
        {children}
        {item ? (
          <ActionBanner
            key={item.id}
            message={item.message}
            icon={item.icon}
            tone={item.tone}
            appearance={appearance}
            onDismiss={dismissHere}
          />
        ) : null}
      </View>
    </ActionFeedbackContext.Provider>
  );
}

const styles = StyleSheet.create({
  host: { flex: 1 },
});

export {
  useActionFeedback,
  useActionFeedbackOptional,
} from "@/contexts/actionFeedbackCore";
