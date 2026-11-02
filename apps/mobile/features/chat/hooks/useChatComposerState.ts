import { useMemo } from "react";

type Options = {
  autoEnabled: boolean;
  modelEnabledSet: Set<string>;
  autoModelId: string;
};

/** Model sent with each message — follows Settings; no per-composer override. */
export function useChatComposerState({
  autoEnabled,
  modelEnabledSet,
  autoModelId,
}: Options) {
  const selectedModel = useMemo(() => {
    if (autoEnabled) return autoModelId;
    const [first] = modelEnabledSet;
    return first ?? autoModelId;
  }, [autoEnabled, autoModelId, modelEnabledSet]);

  return { selectedModel };
}
