import { Href, useRouter } from "expo-router";
import { useTranslation } from "react-i18next";
import type { ReactElement } from "react";
import type { StyleProp, ViewStyle } from "react-native";

import { HeaderButton } from "./HeaderButton";

/**
 * iOS 26 draws a liquid-glass circle behind every custom bar button.
 * Header items have to opt out, or a plain icon still sits in a white well.
 */
export function plainHeaderItems(element: ReactElement | null) {
  if (element == null) return [];
  return [{ type: "custom" as const, hidesSharedBackground: true, element }];
}

/** Back button for a stack screen, without the iOS 26 glass circle. */
export function stackBackOptions(fallback: Href = "/") {
  const element = <StackBackButton fallback={fallback} />;
  return {
    headerLeft: () => element,
    unstable_headerLeftItems: () => plainHeaderItems(element),
  };
}

type Props = {
  /** Where to go when there is no back stack (e.g. opened via deep link). */
  fallback?: Href;
  style?: StyleProp<ViewStyle>;
};

/** Plain back arrow for every stack header — no circular plate. */
export function StackBackButton({ fallback = "/", style }: Props) {
  const router = useRouter();
  const { t } = useTranslation();

  return (
    <HeaderButton
      icon="arrow-left"
      variant="plain"
      accessibilityLabel={t("common.back")}
      onPress={() => {
        if (router.canGoBack()) router.back();
        else router.replace(fallback);
      }}
      style={style}
      testID="stack-back"
    />
  );
}
