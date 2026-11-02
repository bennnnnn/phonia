import { useMemo } from "react";
import { StyleSheet } from "react-native";
import { useTranslation } from "react-i18next";

import { useActionFeedbackOptional } from "@/contexts/actionFeedbackCore";
import { reportRecoverableError } from "@/lib/reportRecoverableError";
import { IconButton } from "@/ui/controls/IconButton";
import { useTheme } from "@/lib/theme";
import { IconSize } from "@/ui/icons/sizes";
import { useCopyText } from "@/ui/share/useCopyText";

type Props = {
  text: string;
  /** Override the a11y label (defaults to "Copy" / "Copied"). */
  accessibilityLabel?: string;
};

const ICON_SIZE = IconSize.sm;

export function CopyButton({
  text,
  accessibilityLabel,
}: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = useMemo(() => makeStyles(), []);
  const feedback = useActionFeedbackOptional();
  const { copied, copy } = useCopyText(() =>
    reportRecoverableError(feedback, t("share.copy_failed")),
  );

  const label = copied ? t("common.copied") : t("common.copy");
  // The same quiet ink as the copy icon under a reply.
  const ink = copied ? theme.primary : theme.textSecondary;

  return (
    <IconButton
      name={copied ? "check" : "copy"}
      size={ICON_SIZE}
      color={ink}
      onPress={() => void copy(text)}
      accessibilityLabel={accessibilityLabel ?? label}
      style={s.btn}
    />
  );
}

function makeStyles() {
  return StyleSheet.create({
    btn: {
      // 44×44 touch target; negative margins keep the visual footprint at the
      // old 32×32 so card headers don't grow.
      width: 44,
      height: 44,
      margin: -6,
    },
  });
}
