import { Component, useMemo, type ErrorInfo, type ReactNode } from "react";
import { StyleSheet, Text } from "react-native";
import { useTranslation } from "react-i18next";

import { reportBoundaryError } from "@/lib/sentry";
import { Space } from "@/lib/space";
import { type Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";

type Props = {
  /** The row's list key: a reused row showing another message starts clean. */
  resetKey: string;
  children: ReactNode;
};

type State = { failed: boolean; resetKey: string };

function RowFallback() {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  return <Text style={s.text}>{t("chat.message_render_failed")}</Text>;
}

/**
 * Keeps a render error inside one chat row. The markdown body has its own
 * boundary; everything else in a bubble (images, places, proposal cards,
 * sources, attachments, the image-gen card) did not, so one bad message
 * reached the root boundary and replaced the whole app.
 */
export class MessageRowErrorBoundary extends Component<Props, State> {
  state: State = { failed: false, resetKey: this.props.resetKey };

  static getDerivedStateFromError(): Pick<State, "failed"> {
    return { failed: true };
  }

  static getDerivedStateFromProps(props: Props, state: State): State | null {
    if (props.resetKey !== state.resetKey) {
      return { failed: false, resetKey: props.resetKey };
    }
    return null;
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (__DEV__) {
      console.warn("[MessageRowErrorBoundary]", error.message, error.stack);
    }
    reportBoundaryError("message_row", error, info.componentStack);
  }

  render() {
    return this.state.failed ? <RowFallback /> : this.props.children;
  }
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    text: {
      ...Type.compact,
      color: theme.textSecondary,
      marginVertical: Space.xs,
      paddingHorizontal: Space.md,
    },
  });
}
