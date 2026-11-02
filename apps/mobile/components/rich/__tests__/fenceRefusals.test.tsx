/**
 * A block that will not draw its fence reports it once: the fence's id and a reason code,
 * never its body (outside review, 2026-11-01). One that draws reports nothing.
 */
import { act, render, renderHook } from "@testing-library/react-native";
import type { ComponentType } from "react";

import { ArrayBlock } from "@/components/rich/ArrayBlock";
import { CalculatorBlock } from "@/components/rich/CalculatorBlock";
import { ChemistrySceneBlock } from "@/components/rich/ChemistrySceneBlock";
import { FunctionGraphBlock } from "@/components/rich/FunctionGraphBlock";
import { GeometryBlock } from "@/components/rich/GeometryBlock";
import { QuizCard } from "@/components/rich/QuizCard";
import { useWebPreviewHeight } from "@/components/rich/useWebPreviewHeight";
import { CHART_PREVIEW_HEIGHT } from "@/lib/chartPreviewHeight";
import { reportFenceRefused } from "@/lib/sentry";

jest.mock("@/lib/sentry", () => ({ reportFenceRefused: jest.fn() }));
jest.mock("@/lib/skiaAvailability", () => ({ isSkiaAvailable: () => false }));
jest.mock("@/ui/icons/Icon", () => ({ Icon: () => null }));
jest.mock("@/lib/haptics", () => ({ selection: jest.fn(), notifySuccess: jest.fn(), notifyWarning: jest.fn() }));

const PRIVATE = "my private homework";

beforeEach(() => jest.clearAllMocks());

describe("a refused fence", () => {
  it.each<[string, ComponentType<{ content: string }>, string, string, string]>([
    ["geometry cut short", GeometryBlock, `{"type": "circle", "label": "${PRIVATE}"`, "geometry", "invalid_json"],
    ["geometry of a shape it does not draw", GeometryBlock, `{"type": "hexagon", "label": "${PRIVATE}"}`, "geometry", "unknown_kind"],
    ["geometry that fails its checks", GeometryBlock, `{"type": "circle", "radius": -1, "label": "${PRIVATE}"}`, "geometry", "invalid_spec"],
    ["a graph in prose", FunctionGraphBlock, `a parabola: ${PRIVATE}`, "graph", "invalid_json"],
    ["a graph kind it does not draw", FunctionGraphBlock, '{"type": "polar", "expr": "r"}', "graph", "unknown_kind"],
    ["a calculator it cannot read", CalculatorBlock, '{"v": 2, "controls": [], "readouts": []}', "calculator", "invalid_spec"],
    ["a chemistry scene of another kind", ChemistrySceneBlock, '{"kind": "nmr", "title": "t"}', "chem_scene", "unknown_kind"],
    ["a quiz written as text", QuizCard, `Which is bigger? ${PRIVATE}`, "quiz", "invalid_json"],
    ["a list whose JSON does not read", ArrayBlock, `{"values": [1, 2,], "note": "${PRIVATE}"}`, "array", "invalid_json"],
  ])("%s: reports its id and reason once, nothing of its body", async (_name, Block, content, fence, reason) => {
    const view = await render(<Block content={content} />);
    await view.rerender(<Block content={content} />);

    expect(reportFenceRefused).toHaveBeenCalledTimes(1);
    expect(reportFenceRefused).toHaveBeenCalledWith(fence, reason);
    expect(JSON.stringify(jest.mocked(reportFenceRefused).mock.calls)).not.toContain(PRIVATE);
  });

  it("is not reported for a fence that draws", async () => {
    await render(<GeometryBlock content='{"type": "rectangle", "width": 6, "height": 4}' />);
    await render(
      <FunctionGraphBlock content='{"type": "function", "expr": "x", "points": [[0, 0], [1, 1]]}' />,
    );
    await render(<ArrayBlock content='{"values": [1, 2]}' />);
    expect(reportFenceRefused).not.toHaveBeenCalled();
  });

  it("is reported when a chart's or diagram's page cannot draw, without the page's message", async () => {
    const { result } = await renderHook(() =>
      useWebPreviewHeight({ rules: CHART_PREVIEW_HEIGHT, page: "chart", errorText: "rich.chart_error" }),
    );
    await act(async () => {
      result.current.onMessage({ nativeEvent: { data: JSON.stringify({ kind: "chart-error", message: PRIVATE }) } });
    });
    expect(result.current.renderError).toBe(PRIVATE);
    expect(reportFenceRefused).toHaveBeenCalledWith("chart", "draw_failed");
    expect(JSON.stringify(jest.mocked(reportFenceRefused).mock.calls)).not.toContain(PRIVATE);
  });
});
