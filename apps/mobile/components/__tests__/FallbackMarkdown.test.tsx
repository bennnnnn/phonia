import { render, screen } from "@testing-library/react-native";

import { FallbackMarkdown } from "@/components/FallbackMarkdown";

const mockLoaded: string[] = [];

jest.mock("@/components/rich/GeometryBlock", () => {
  const { createElement } = jest.requireActual<typeof import("react")>("react");
  const { Text } = jest.requireActual<typeof import("react-native")>("react-native");
  mockLoaded.push("geometry");
  return {
    GeometryBlock: ({ content }: { content: string }) => createElement(Text, null, `geometry ${content}`),
  };
});

jest.mock("@/components/rich/FunctionGraphBlock", () => {
  const { createElement } = jest.requireActual<typeof import("react")>("react");
  const { Text } = jest.requireActual<typeof import("react-native")>("react-native");
  mockLoaded.push("graph");
  return {
    FunctionGraphBlock: ({ content }: { content: string }) => createElement(Text, null, `graph ${content}`),
  };
});

describe("FallbackMarkdown", () => {
  it("draws geometry and graph fences with renderers it loads only when one is shown", async () => {
    await render(<FallbackMarkdown content="Plain words only." />);
    expect(screen.getByText("Plain words only.")).toBeOnTheScreen();
    expect(mockLoaded).toEqual([]);

    await render(
      <FallbackMarkdown
        content={'Here:\n\n```geometry\n{"type":"rectangle"}\n```\n\n```graph\n{"fn":"x"}\n```\n'}
      />,
    );

    expect(await screen.findByText('geometry {"type":"rectangle"}')).toBeOnTheScreen();
    expect(await screen.findByText('graph {"fn":"x"}')).toBeOnTheScreen();
    expect(mockLoaded.sort()).toEqual(["geometry", "graph"]);
  });
});
