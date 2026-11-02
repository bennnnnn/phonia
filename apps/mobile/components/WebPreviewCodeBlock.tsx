import React, { Suspense, useMemo, useState } from "react";
import { StyleSheet, TouchableOpacity, View } from "react-native";
import { useTranslation } from "react-i18next";

import { Icon } from "@/ui/icons/Icon";
import { CodeBlock } from "@/components/CodeBlock";
import { bundleHtmlPreview, previewHasSiblingAssets } from "@/lib/preview/htmlPreviewBundle";
import { useHtmlPreviewFiles } from "@/lib/preview/htmlPreviewFiles";
import { openHtmlInBrowser } from "@/lib/preview/openHtmlPreview";
import { Theme, useTheme } from "@/lib/theme";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { IconSize } from "@/ui/icons/sizes";

const HtmlPreviewModalLazy = React.lazy(() =>
  import("@/components/HtmlPreviewModal").then((m) => ({
    default: m.HtmlPreviewModal,
  })),
);

type Props = {
  code: string;
  lang?: string;
};

/** HTML fence: syntax-highlighted code + preview modal + bottom actions. */
export function WebPreviewCodeBlock({ code, lang = "html" }: Props) {
  const theme = useTheme();
  const { t } = useTranslation();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const [modalOpen, setModalOpen] = useState(false);
  const siblingFiles = useHtmlPreviewFiles();
  // Bundled only for the open preview or the browser: while the reply streams,
  // the other fences change around a closed block that nobody has opened.
  const previewHtml = useMemo(
    () => (modalOpen ? bundleHtmlPreview(code, siblingFiles) : ""),
    [modalOpen, code, siblingFiles],
  );
  const previewLabel = previewHasSiblingAssets(siblingFiles)
    ? t("preview.preview_html_bundled")
    : t("preview.preview_html");

  return (
    <>
      <CodeBlock
        code={code}
        lang={lang}
        headerExtra={
          <TouchableOpacity
            style={[s.iconBtn, modalOpen && s.iconBtnActive]}
            onPress={() => setModalOpen(true)}
            activeOpacity={0.6}
            hitSlop={4}
            accessibilityRole="button"
            accessibilityLabel={previewLabel}
          >
            <Icon
              name="play"
              size={IconSize.xs}
              color={modalOpen ? theme.primary : theme.textSecondary}
            />
          </TouchableOpacity>
        }
        footerExtra={
          <View style={s.footerActions}>
            <TouchableOpacity
              style={s.iconBtn}
              onPress={() => setModalOpen(true)}
              activeOpacity={0.6}
              hitSlop={4}
              accessibilityRole="button"
              accessibilityLabel={previewLabel}
            >
              <Icon name="play" size={IconSize.sm} color={theme.textSecondary} />
            </TouchableOpacity>
            <TouchableOpacity
              style={s.iconBtn}
              onPress={() => void openHtmlInBrowser(bundleHtmlPreview(code, siblingFiles))}
              activeOpacity={0.6}
              hitSlop={4}
              accessibilityRole="button"
              accessibilityLabel={t("preview.open_in_browser")}
            >
              <Icon name="external-link" size={IconSize.sm} color={theme.textSecondary} />
            </TouchableOpacity>
          </View>
        }
      />

      {modalOpen ? (
        <Suspense fallback={null}>
          <HtmlPreviewModalLazy visible html={previewHtml} onClose={() => setModalOpen(false)} />
        </Suspense>
      ) : null}
    </>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    footerActions: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.xxs,
    },
    iconBtn: {
      width: 44,
      height: 44,
      borderRadius: Radius.xs,
      alignItems: "center",
      justifyContent: "center",
    },
    iconBtnActive: {
      backgroundColor: t.primaryLight,
    },
  });
}
