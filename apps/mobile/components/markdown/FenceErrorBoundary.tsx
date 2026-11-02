import { Component, type ErrorInfo, type ReactNode } from "react";
import { StyleSheet, Text, View } from "react-native";
import { useTranslation } from "react-i18next";

import { FallbackFence } from "@/components/FallbackMarkdown";
import type { FenceReportName } from "@/lib/fenceReports";
import { reportFenceCrash } from "@/lib/sentry";
import { Space } from "@/lib/space";
import { useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";
import { Icon } from "@/ui/icons/Icon";
import { IconSize } from "@/ui/icons/sizes";

/**
 * The fence's language and body: a block drawn from new ones starts clean. `fence` names
 * it in a crash report (`lib/fenceReports.ts`); the language and body never leave the phone.
 */
type Props = { lang: string; content: string; fence: FenceReportName; children: ReactNode };

type State = { failed: boolean; source: string };

const sourceOf = (props: Props) => `${props.lang}\n${props.content}`;

/** One quiet line over the fallback, as a chart that cannot draw says so (ChartFallback). */
function FenceFallbackNote() {
  const { t } = useTranslation();
  const theme = useTheme();
  return (
    <View style={styles.note}>
      <Icon name="alert-circle" size={IconSize.sm} color={theme.textSecondary} />
      <Text style={[styles.noteText, { color: theme.textSecondary }]}>
        {t("rich.block_render_failed")}
      </Text>
    </View>
  );
}

/**
 * Keeps a render error inside one fenced block of a reply. Without it a chart,
 * quiz or molecule that threw reached the reply's boundary
 * (`MarkdownErrorBoundary`), and the whole reply, its prose and every other
 * block, dropped to plain markdown. Now only this block degrades: a note, then
 * the block as that crash fallback draws it (`FallbackFence`: code as plain
 * code, a chart or molecule named, never a JSON dump). Reported once, tagged with the
 * fence's id and never its body.
 */
export class FenceErrorBoundary extends Component<Props, State> {
  state: State = { failed: false, source: sourceOf(this.props) };

  static getDerivedStateFromError(): Pick<State, "failed"> {
    return { failed: true };
  }

  static getDerivedStateFromProps(props: Props, state: State): State | null {
    const source = sourceOf(props);
    return source === state.source ? null : { failed: false, source };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (__DEV__) {
      console.warn("[FenceErrorBoundary]", error.message, error.stack);
    }
    reportFenceCrash(this.props.fence, error, info.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <View>
        <FenceFallbackNote />
        <FallbackFence lang={this.props.lang} content={this.props.content} />
      </View>
    );
  }
}

const styles = StyleSheet.create({
  note: {
    flexDirection: "row",
    alignItems: "center",
    gap: Space.xs,
    marginBottom: Space.xs,
  },
  noteText: { ...Type.compact, flexShrink: 1 },
});
