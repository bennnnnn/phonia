import { useMemo } from "react";
import { StyleSheet, Text } from "react-native";
import { useTranslation } from "react-i18next";

import { CardShell } from "@/components/rich/CardShell";
import { BrandMark, type BrandName } from "@/ui/icons/brand";
import { IconSize } from "@/ui/icons/sizes";
import { SocialPlatform } from "@/lib/richBlocks";
import { Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";

type Props = { text: string; platform: SocialPlatform };

function platformMeta(
  t: (key: string) => string,
): Record<SocialPlatform, { label: string; brand?: BrandName }> {
  return {
    twitter: { label: t("rich.post_draft_x"), brand: "x" },
    linkedin: { label: t("rich.post_draft_linkedin"), brand: "linkedin" },
    facebook: { label: t("rich.post_draft_facebook"), brand: "facebook" },
    instagram: { label: t("rich.post_draft_instagram"), brand: "instagram" },
    generic: { label: t("rich.social_post_draft") },
  };
}

export function SocialPostCard({ text, platform }: Props) {
  const theme = useTheme();
  const { t } = useTranslation();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const meta = platformMeta(t)[platform];
  const sanitized = useMemo(() => text.trim(), [text]);

  return (
    <CardShell
      label={meta.label}
      copyText={sanitized}
      icon={meta.brand ? undefined : "megaphone"}
      leading={
        meta.brand ? <BrandMark name={meta.brand} size={IconSize.sm} color={theme.text} /> : undefined
      }
      accent={false}
    >
      <Text style={s.body} selectable>
        {sanitized}
      </Text>
    </CardShell>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    body: { ...Type.body, color: t.text },
  });
}
