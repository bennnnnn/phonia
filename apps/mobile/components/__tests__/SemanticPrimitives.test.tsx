import { StyleSheet } from "react-native";
import { render } from "@testing-library/react-native";

import { CountBadge } from "@/ui/feedback/CountBadge";
import { lightTheme as mockLightTheme } from "@/lib/theme";

jest.mock("@/lib/theme", () => ({
  ...jest.requireActual("@/lib/theme"),
  useTheme: () => mockLightTheme,
}));

describe("semantic primitives", () => {
  it("uses danger ink and grows count badges with Dynamic Type", async () => {
    const { getByText } = await render(
      <CountBadge count={120} max={99} tone="danger" />,
    );
    const label = getByText("99+");
    const badgeStyle = StyleSheet.flatten(label.parent?.props.style);
    const labelStyle = StyleSheet.flatten(label.props.style);

    expect(badgeStyle).toMatchObject({
      minWidth: 18,
      minHeight: 18,
      backgroundColor: mockLightTheme.danger,
    });
    expect(badgeStyle.height).toBeUndefined();
    expect(labelStyle.color).toBe(mockLightTheme.onDanger);
    expect(labelStyle.lineHeight).toBeUndefined();
  });
});
