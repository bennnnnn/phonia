/**
 * GFM task lists (`- [ ]` / `- [x]`) draw as checkboxes. A list of done
 * items only is a run of verified checks and keeps its trailing tick.
 */
import { render } from "@testing-library/react-native";

import { MarkdownContent } from "@/components/MarkdownContent";

jest.mock("@/components/LinkPreviewCard", () => ({ LinkPreviewCard: () => null }));
jest.mock("expo-web-browser", () => ({ openBrowserAsync: jest.fn() }));
jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  writeAsStringAsync: jest.fn(),
  EncodingType: { UTF8: "utf8" },
}));

const PACKING = ["### Clothing", "- [ ] Rain jacket", "- [x] Hiking boots", "- [ ] Warm hat"].join("\n");

describe("markdown task lists", () => {
  it("draws each item as a checkbox, ticked when done", async () => {
    const { getAllByTestId, getAllByRole, getByText, queryByText } = await render(
      <MarkdownContent content={PACKING} />,
    );
    expect(getAllByTestId("md-task-open")).toHaveLength(2);
    expect(getAllByTestId("md-task-done")).toHaveLength(1);
    const boxes = getAllByRole("checkbox");
    expect(boxes.map((box) => box.props.accessibilityState?.checked)).toEqual([false, true, false]);
    // No literal brackets, and no stray space before the label.
    expect(queryByText(/\[ \]|\[x\]/)).toBeNull();
    expect(getByText("Rain jacket")).toBeOnTheScreen();
  });

  it("keeps the trailing verified tick on a list of done checks", async () => {
    const { queryByTestId, queryAllByRole, getByText } = await render(
      <MarkdownContent content={"- [x] Left side: 6\n- [x] Right side: 6"} />,
    );
    expect(queryByTestId("md-task-done")).toBeNull();
    expect(queryAllByRole("checkbox")).toHaveLength(0);
    expect(getByText("Left side: 6")).toBeOnTheScreen();
  });
});
