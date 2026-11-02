import { Text } from "react-native";
import { render } from "@testing-library/react-native";

import { AUTH_COLUMN_MAX_WIDTH, AuthScrollLayout } from "@/components/AuthScrollLayout";

jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 12, bottom: 20, left: 0, right: 0 }),
}));

describe("AuthScrollLayout", () => {
  it("scrolls with flexGrow so short auth screens still fill the viewport", async () => {
    const { getByTestId, getByText } = await render(
      <AuthScrollLayout>
        <Text>sign in</Text>
      </AuthScrollLayout>,
    );

    expect(getByText("sign in")).toBeOnTheScreen();
    expect(getByTestId("auth-scroll-layout")).toBeTruthy();
  });

  it("caps the column width for tablet gutters", () => {
    expect(AUTH_COLUMN_MAX_WIDTH).toBe(420);
  });
});
