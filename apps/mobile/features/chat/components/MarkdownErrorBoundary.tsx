import { Component, type ErrorInfo, ReactNode } from "react";
import { Text } from "react-native";

import { FallbackMarkdown } from "@/components/FallbackMarkdown";
import { reportBoundaryError } from "@/lib/sentry";
import { useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";

type Props = {
  resetKey: string;
  content: string;
  children: ReactNode;
};

type State = { failed: boolean; resetKey: string };

type PlainState = { failed: boolean };

/** The raw reply in body type and the theme's ink (bare Text was black in dark mode). */
function PlainFallbackText({ content }: { content: string }) {
  const t = useTheme();
  return <Text style={[Type.body, { color: t.assistantText }]}>{content}</Text>;
}

/** Last resort if FallbackMarkdown itself throws — keep the crash in the bubble. */
class PlainTextErrorBoundary extends Component<{ content: string; children: ReactNode }, PlainState> {
  state: PlainState = { failed: false };

  static getDerivedStateFromError(): PlainState {
    return { failed: true };
  }

  render() {
    if (this.state.failed) {
      return <PlainFallbackText content={this.props.content} />;
    }
    return this.props.children;
  }
}

export class MarkdownErrorBoundary extends Component<Props, State> {
  state: State = { failed: false, resetKey: this.props.resetKey };

  static getDerivedStateFromError(): Pick<State, "failed"> {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (__DEV__) {
      console.warn("[MarkdownErrorBoundary]", error.message, error.stack);
    }
    reportBoundaryError("markdown", error, info.componentStack);
  }

  static getDerivedStateFromProps(props: Props, state: State): State | null {
    if (props.resetKey !== state.resetKey) {
      return { failed: false, resetKey: props.resetKey };
    }
    return null;
  }

  render() {
    if (this.state.failed) {
      return (
        <PlainTextErrorBoundary key={this.props.resetKey} content={this.props.content}>
          <FallbackMarkdown content={this.props.content} />
        </PlainTextErrorBoundary>
      );
    }
    return this.props.children;
  }
}
