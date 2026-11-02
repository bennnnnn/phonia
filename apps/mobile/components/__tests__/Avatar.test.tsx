import { act, render } from "@testing-library/react-native";

import { Avatar } from "@/components/Avatar";

jest.mock("@/lib/config", () => ({ getApiUrl: () => "https://api.recall.test" }));

describe("profile photo loading", () => {
  it("authenticates an uploaded photo on Recall's API", async () => {
    const { getByTestId } = await render(
      <Avatar name="Bini" uri="/attachments/11111111-1111-4111-8111-111111111111/file" token="test-token" />,
    );
    expect(getByTestId("avatar-image").props.source).toEqual({
      uri: "https://api.recall.test/attachments/11111111-1111-4111-8111-111111111111/file",
      headers: { Authorization: "Bearer test-token" },
    });
  });

  it.each(["https://provider.test/photo.jpg", "file:///local-preview.jpg"])(
    "does not send account credentials to %s",
    async (uri) => {
      const { getByTestId } = await render(<Avatar name="Bini" uri={uri} token="test-token" />);
      expect(getByTestId("avatar-image").props.source).toEqual({ uri, headers: {} });
    },
  );
});

describe("a photo that will not load", () => {
  it("shows the initials instead of a blank circle", async () => {
    const view = await render(<Avatar name="Bini Mecuriaw" uri="https://provider.test/gone.jpg" />);
    await act(async () => {
      view.getByTestId("avatar-image").props.onError({ error: "404" });
    });
    expect(view.queryByTestId("avatar-image")).toBeNull();
    expect(view.getByText("BM")).toBeOnTheScreen();
  });
});
