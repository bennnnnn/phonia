import { render } from "@testing-library/react-native";

import { StateView } from "../StateView";
import { lightTheme as mockLightTheme } from "@/lib/theme";

jest.mock("@/lib/theme", () => ({
  ...jest.requireActual("@/lib/theme"),
  useTheme: () => mockLightTheme,
}));

jest.mock("@/lib/haptics", () => ({
  tap: jest.fn(),
}));

jest.mock("@/ui/icons/Icon", () => {
  const { Text } = jest.requireActual("react-native") as typeof import("react-native");
  return {
    Icon: ({ name }: { name: string }) => <Text>{name}</Text>,
  };
});

describe("StateView", () => {
  it("uses a generic alert icon for errors, not a cloud-offline glyph", async () => {
    const { getByText, queryByText } = await render(
      <StateView variant="error" title="common.error" />,
    );

    expect(getByText("alert-circle")).toBeTruthy();
    expect(queryByText("cloud-off")).toBeNull();
  });

  it("keeps an explicit connectivity icon when the caller passes one", async () => {
    const { getByText } = await render(
      <StateView variant="error" icon="cloud-off" message="drawer.cant_reach" />,
    );

    expect(getByText("cloud-off")).toBeTruthy();
  });

  it("names its state with a heading a screen reader can jump to", async () => {
    const { getByRole } = await render(<StateView variant="empty" title="No chats yet" />);
    expect(getByRole("header", { name: "No chats yet" })).toBeOnTheScreen();
  });
});
