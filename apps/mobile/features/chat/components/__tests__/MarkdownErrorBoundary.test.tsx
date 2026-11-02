import type { ReactNode } from "react";
import { Text } from "react-native";
import { render } from "@testing-library/react-native";

import { MarkdownErrorBoundary } from "@/features/chat/components/MarkdownErrorBoundary";

jest.mock("@/components/FallbackMarkdown", () => ({
  FallbackMarkdown: () => {
    throw new Error("fallback boom");
  },
}));

function Boom(): ReactNode {
  throw new Error("rich boom");
}

describe("MarkdownErrorBoundary", () => {
  const warn = jest.spyOn(console, "warn").mockImplementation(() => undefined);
  const error = jest.spyOn(console, "error").mockImplementation(() => undefined);

  afterAll(() => {
    warn.mockRestore();
    error.mockRestore();
  });

  it("renders plain text when FallbackMarkdown also throws", async () => {
    const { getByText } = await render(
      <MarkdownErrorBoundary resetKey="1" content="plain bubble copy">
        <Boom />
      </MarkdownErrorBoundary>,
    );
    expect(getByText("plain bubble copy")).toBeTruthy();
  });

  it("renders children when markdown does not throw", async () => {
    const { getByText } = await render(
      <MarkdownErrorBoundary resetKey="ok" content="unused">
        <Text>ok children</Text>
      </MarkdownErrorBoundary>,
    );
    expect(getByText("ok children")).toBeTruthy();
  });
});
