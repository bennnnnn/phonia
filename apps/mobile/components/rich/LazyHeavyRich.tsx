/**
 * Async-split Mermaid (~3.4MB), Vega (~0.85MB), SmilesDrawer (~0.25MB),
 * Web preview, clock, geometry/graph SVG blocks, physics scenes and the
 * parsers that size a scene's placeholder off the chat import graph.
 */
import React, { Suspense, useEffect, useMemo, useState, type ComponentType } from "react";
import { ActivityIndicator, useWindowDimensions, View } from "react-native";

import { diagramKind } from "@/lib/physics/diagramKind";
import { SIMULATION_HEIGHT } from "@/lib/physics/simulation/viewport";

/** The height each block's spinner holds while its chunk loads, close to the drawn card. */
const PLACEHOLDER_HEIGHT = {
  mermaid: 220,
  chart: 350,
  chemistry: 240,
  molecule: 240,
  molecule3d: 280,
  geometry: 220,
  graph: 280,
  clock: 340,
} as const;

/** A web preview's spinner: its chrome plus up to 14 visible code lines. */
const WEB_PREVIEW_CHROME_HEIGHT = 112;
const WEB_PREVIEW_LINE_HEIGHT = 20;
const WEB_PREVIEW_MAX_LINES = 14;

const SimulationBlockLazy = React.lazy(() =>
  import("@/components/rich/SimulationBlock").then((m) => ({
    default: m.SimulationBlock,
  })),
);

const PhysicsDiagramLazy = React.lazy(() =>
  import("@/components/rich/diagrams/PhysicsDiagram").then((m) => ({
    default: m.PhysicsDiagram,
  })),
);

const WebPreviewCodeBlockLazy = React.lazy(() =>
  import("@/components/WebPreviewCodeBlock").then((m) => ({
    default: m.WebPreviewCodeBlock,
  })),
);

function RichLoadPlaceholder({ height }: { height: number }) {
  return (
    <View testID="rich-load-placeholder" style={{ height, alignItems: "center", justifyContent: "center" }}>
      <ActivityIndicator />
    </View>
  );
}

type ContentBlockProps = { content: string };

/**
 * A block drawn from a fence body, loaded on first use behind a spinner of
 * `height`. The `import()` stays a literal at each call so Metro splits it.
 */
function lazyContentBlock(
  load: () => Promise<{ default: ComponentType<ContentBlockProps> }>,
  height: number,
): ComponentType<ContentBlockProps> {
  const Block = React.lazy(load);
  return function LazyContentBlock({ content }: ContentBlockProps) {
    return (
      <Suspense fallback={<RichLoadPlaceholder height={height} />}>
        <Block content={content} />
      </Suspense>
    );
  };
}

export const LazyMermaidBlock = lazyContentBlock(
  () => import("@/components/rich/MermaidBlock").then((m) => ({ default: m.MermaidBlock })),
  PLACEHOLDER_HEIGHT.mermaid,
);

export const LazyChartBlock = lazyContentBlock(
  () => import("@/components/rich/ChartBlock").then((m) => ({ default: m.ChartBlock })),
  PLACEHOLDER_HEIGHT.chart,
);

export const LazyChemistryBlock = lazyContentBlock(
  () => import("@/components/rich/ChemistryBlock").then((m) => ({ default: m.ChemistryBlock })),
  PLACEHOLDER_HEIGHT.chemistry,
);

export const LazyMoleculeCard = lazyContentBlock(
  () => import("@/components/rich/MoleculeCard").then((m) => ({ default: m.MoleculeCard })),
  PLACEHOLDER_HEIGHT.molecule,
);

export const LazyMolecule3DBlock = lazyContentBlock(
  () => import("@/components/rich/Molecule3DBlock").then((m) => ({ default: m.Molecule3DBlock })),
  PLACEHOLDER_HEIGHT.molecule3d,
);

export const LazyGeometryBlock = lazyContentBlock(
  () => import("@/components/rich/GeometryBlock").then((m) => ({ default: m.GeometryBlock })),
  PLACEHOLDER_HEIGHT.geometry,
);

export const LazyFunctionGraphBlock = lazyContentBlock(
  () =>
    import("@/components/rich/FunctionGraphBlock").then((m) => ({
      default: m.FunctionGraphBlock,
    })),
  PLACEHOLDER_HEIGHT.graph,
);

export const LazyCircularClockBlock = lazyContentBlock(
  () =>
    import("@/components/rich/CircularClockBlock").then((m) => ({
      default: m.CircularClockBlock,
    })),
  PLACEHOLDER_HEIGHT.clock,
);

type SimulationSizing = typeof import("@/components/rich/simulationPlaceholder");

/** The fence's exact placeholder height comes from the physics parsers, loaded on first use. */
let simulationSizing: SimulationSizing | null = null;
let simulationSizingLoad: Promise<SimulationSizing> | null = null;

function loadSimulationSizing(): Promise<SimulationSizing> {
  simulationSizingLoad ??= import("@/components/rich/simulationPlaceholder").then(
    (sizing) => {
      simulationSizing = sizing;
      return sizing;
    },
    (error: unknown) => {
      simulationSizingLoad = null;
      throw error;
    },
  );
  return simulationSizingLoad;
}

/**
 * Loads the sizing parsers ahead of the first scene (the root layout calls this
 * once the launch has settled), so that scene's placeholder is its own height
 * from the start instead of the usual one for a frame.
 */
export function preloadSimulationSizing(): void {
  loadSimulationSizing().catch(() => {});
}

/** The sizing module once loaded; the first scene of a session asks for it. */
function useSimulationSizing(): SimulationSizing | null {
  const [sizing, setSizing] = useState(simulationSizing);
  useEffect(() => {
    if (sizing) return;
    let current = true;
    loadSimulationSizing().then(
      (loaded) => {
        if (current) setSizing(loaded);
      },
      () => {},
    );
    return () => {
      current = false;
    };
  }, [sizing]);
  return sizing;
}

export function LazySimulationBlock({ content }: { content: string }) {
  const { width: screenWidth } = useWindowDimensions();
  // A circuit, a ray diagram or a wave has no bodies to walk: its own renderer.
  const kind = useMemo(() => diagramKind(content), [content]);
  const sizing = useSimulationSizing();
  // Until the sizing module is in (a moment, once per session), the usual scene height.
  const height = useMemo(
    () =>
      sizing
        ? sizing.simulationFencePlaceholderHeight(content, kind, screenWidth)
        : SIMULATION_HEIGHT,
    [content, kind, screenWidth, sizing],
  );
  return (
    <Suspense fallback={<RichLoadPlaceholder height={height} />}>
      {kind ? (
        <PhysicsDiagramLazy content={content} kind={kind} />
      ) : (
        <SimulationBlockLazy content={content} />
      )}
    </Suspense>
  );
}

export function LazyWebPreviewCodeBlock({
  code,
  lang = "html",
}: {
  code: string;
  lang?: string;
}) {
  const visibleLines = Math.min(code.split("\n").length, WEB_PREVIEW_MAX_LINES);
  const placeholderHeight = WEB_PREVIEW_CHROME_HEIGHT + visibleLines * WEB_PREVIEW_LINE_HEIGHT;
  return (
    <Suspense fallback={<RichLoadPlaceholder height={placeholderHeight} />}>
      <WebPreviewCodeBlockLazy code={code} lang={lang} />
    </Suspense>
  );
}
