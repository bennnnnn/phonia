import { StyleSheet, type StyleProp, type TextStyle } from "react-native";
import { render } from "@testing-library/react-native";

import { SocialPostCard } from "@/components/rich/SocialPostCard";
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

describe("SocialPostCard", () => {
  it("does not paint a brand left stripe (same chrome as the SMS draft)", async () => {
    const { getByText } = await render(
      <SocialPostCard
        platform="linkedin"
        text="Excited to share that we've shipped a small product improvement."
      />,
    );
    const label = getByText("rich.post_draft_linkedin");
    let node: { parent?: unknown; props?: { style?: StyleProp<TextStyle> } } | undefined =
      label;
    let sawBrandAccent = false;
    while (node) {
      const flat = StyleSheet.flatten(node.props?.style);
      if (
        flat?.borderLeftColor === lightTheme.brand.linkedin ||
        flat?.borderLeftColor === lightTheme.primary
      ) {
        sawBrandAccent = true;
        break;
      }
      node = node.parent as typeof node;
    }
    expect(sawBrandAccent).toBe(false);
  });

  it("renders draft copy without a fake You / avatar row", async () => {
    const { getByText, queryByText } = await render(
      <SocialPostCard platform="linkedin" text="Shipped this week." />,
    );
    expect(getByText("Shipped this week.")).toBeTruthy();
    expect(queryByText("common.you")).toBeNull();
  });

  it("preserves a template placeholder instead of leaving a grammar hole", async () => {
    const { getByText, queryByText } = await render(
      <SocialPostCard
        platform="linkedin"
        text="Thrilled to welcome [New Hire's Name] to the team."
      />,
    );
    expect(
      getByText("Thrilled to welcome [New Hire's Name] to the team."),
    ).toBeTruthy();
    expect(queryByText("Thrilled to welcome  to the team.")).toBeNull();
  });
});
