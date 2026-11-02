import { StyleSheet, type StyleProp, type TextStyle } from "react-native";
import { render } from "@testing-library/react-native";

import { MessagePreview } from "@/components/rich/MessagePreview";
import { lightTheme } from "@/lib/theme";

jest.mock("react-native-svg", () => {
  const { View } = jest.requireActual("react-native") as typeof import("react-native");
  return {
    __esModule: true,
    default: View,
    Svg: View,
    Path: View,
    Circle: View,
    Rect: View,
    Line: View,
    Polyline: View,
    Polygon: View,
    Ellipse: View,
    Defs: View,
    Mask: View,
  };
});

describe("MessagePreview", () => {
  it("renders draft copy on a white card, not a brand-blue bubble", async () => {
    const { getByText } = await render(
      <MessagePreview text="Hey Sam! 👋" />,
    );
    const text = getByText("Hey Sam! 👋");
    expect(StyleSheet.flatten(text.props.style)).toMatchObject({
      color: lightTheme.text,
    });
    let node: { parent?: unknown; props?: { style?: StyleProp<TextStyle> } } | undefined =
      text;
    let cardFill: string | undefined;
    while (node) {
      const fill = StyleSheet.flatten(node.props?.style)?.backgroundColor;
      if (typeof fill === "string") {
        cardFill = fill;
        break;
      }
      node = node.parent as typeof node;
    }
    expect(cardFill).toBe(lightTheme.surface);
    expect(cardFill).not.toBe(lightTheme.primary);
  });

  it("does not show a Preview caption under the draft", async () => {
    const { queryByText } = await render(
      <MessagePreview text="Hey [Friend's Name]! 👋" />,
    );
    expect(queryByText("rich.preview")).toBeNull();
    expect(queryByText(/^Preview$/i)).toBeNull();
  });

  it("does not paint a brand-blue left stripe on the draft card", async () => {
    const { getByText } = await render(
      <MessagePreview text="Hey [Friend's Name]! 👋" />,
    );
    const label = getByText("rich.message_draft");
    let node: { parent?: unknown; props?: { style?: StyleProp<TextStyle> } } | undefined =
      label;
    let sawPrimaryAccent = false;
    while (node) {
      const flat = StyleSheet.flatten(node.props?.style);
      if (flat?.borderLeftColor === lightTheme.primary) {
        sawPrimaryAccent = true;
        break;
      }
      node = node.parent as typeof node;
    }
    expect(sawPrimaryAccent).toBe(false);
  });

  it("preserves explicit template placeholders without broken grammar", async () => {
    const { getByText, queryByText } = await render(
      <MessagePreview text="Hey [Friend's Name]! 👋" />,
    );
    expect(getByText("Hey [Friend's Name]! 👋")).toBeTruthy();
    expect(queryByText("Hey ! 👋")).toBeNull();
  });
});
