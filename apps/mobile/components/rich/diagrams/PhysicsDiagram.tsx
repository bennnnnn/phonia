/**
 * The physics scenes with no moving bodies: a circuit schematic, a ray
 * diagram, a wave. `LazyHeavyRich` routes a `simulation` fence of type
 * `circuit`, `rays` or `wave` here; everything else is `SimulationBlock`'s.
 *
 * The phone never does physics. The server sends the network, the traced rays
 * and the sampled wave frames; these renderers only lay them out and draw.
 */
import { useMemo } from "react";

import { CircuitDiagram } from "@/components/rich/diagrams/CircuitDiagram";
import { DiagramFallback } from "@/components/rich/diagrams/DiagramFrame";
import { RayDiagram } from "@/components/rich/diagrams/RayDiagram";
import { parsePhysicsDiagram } from "@/components/rich/diagrams/spec";
import { WaveDiagram } from "@/components/rich/diagrams/WaveDiagram";
import { useFenceRefused } from "@/components/rich/useFenceRefused";
import { type DiagramKind } from "@/lib/physics/diagramKind";

export function PhysicsDiagram({ content, kind }: { content: string; kind: DiagramKind }) {
  const spec = useMemo(() => parsePhysicsDiagram(content, kind), [content, kind]);
  // Its kind was read to route it here: what failed is the rest of the body.
  useFenceRefused("simulation", content, spec === null, undefined, "invalid_spec");
  if (!spec) return <DiagramFallback />;
  switch (spec.kind) {
    case "circuit":
      return <CircuitDiagram spec={spec} />;
    case "rays":
      return <RayDiagram spec={spec} />;
    case "wave":
      return <WaveDiagram spec={spec} content={content} />;
  }
}
