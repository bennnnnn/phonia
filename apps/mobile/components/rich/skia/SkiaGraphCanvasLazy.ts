import { lazy } from "react";

/**
 * The Skia function plot, loaded on first use. Skia stays out of the import
 * graph unless a native graph actually renders (Expo Go and stale clients
 * keep the SVG compatibility path). The plot card and its explorer share this
 * one instance, so the explorer never waits for a module the card loaded.
 */
export const SkiaGraphCanvasLazy = lazy(() =>
  import("@/components/rich/skia/SkiaGraphExplorer").then((m) => ({
    default: m.SkiaGraphCanvas,
  })),
);
