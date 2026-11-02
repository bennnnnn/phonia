import { useEffect } from "react";
import { AccessibilityInfo, Platform } from "react-native";

/**
 * The iOS half of a live region. `accessibilityLiveRegion` is Android-only, so text that
 * appears beside a control (a result, an error, a toast) is silent for VoiceOver unless
 * it is announced. Pass the text while it is shown, `null` otherwise; it is spoken when
 * it appears or changes. TalkBack keeps reading the element's live region.
 */
export function useLiveAnnouncement(text: string | null | undefined): void {
  useEffect(() => {
    if (text && Platform.OS === "ios") AccessibilityInfo.announceForAccessibility(text);
  }, [text]);
}
