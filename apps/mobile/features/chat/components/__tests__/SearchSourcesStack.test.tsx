import { fireEvent, render } from "@testing-library/react-native";

import { SearchSourcesStack } from "@/features/chat/components/SearchSourcesStack";

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { count?: number }) =>
      key === "chat.sources_count" ? `${opts?.count} sources` : key,
  }),
}));

jest.mock("@/lib/reduceMotion", () => ({
  useReduceMotion: () => false,
}));

jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 34, left: 0, right: 0 }),
}));

describe("SearchSourcesStack", () => {
  it("caches favicons and falls back to the host letter after load failure", async () => {
    const { getByTestId, getByText, queryByTestId } = await render(
      <SearchSourcesStack
        sources={[
          {
            url: "https://example.com/rain",
            title: "Rainfall averages",
          },
        ]}
      />,
    );

    const favicon = getByTestId("search-source-favicon");
    expect(favicon.props.source).toEqual({
      uri: "https://www.google.com/s2/favicons?domain=example.com&sz=64",
    });
    expect(favicon.props.contentFit).toBe("contain");
    expect(favicon.props.cachePolicy).toBe("memory-disk");

    await fireEvent(favicon, "error");
    expect(queryByTestId("search-source-favicon")).toBeNull();
    expect(getByText("E")).toBeTruthy();
  });

  it("opens sources in Sheet with a scrollable list", async () => {
    const { getByText, getByTestId } = await render(
      <SearchSourcesStack
        sources={[
          {
            url: "https://example.com/rain",
            title: "Rainfall averages",
            snippet: "January through December",
          },
        ]}
      />,
    );

    await fireEvent.press(getByText("1 sources"));

    expect(getByTestId("app-sheet-handle")).toBeTruthy();
    expect(getByTestId("app-sheet-dialog")).toBeTruthy();
    expect(getByText("Rainfall averages")).toBeTruthy();
  });
});
