import { createContext, useContext, type ReactNode } from "react";

import type { PreviewFile } from "@/lib/preview/htmlPreviewBundle";

const HtmlPreviewFilesContext = createContext<PreviewFile[]>([]);

export function HtmlPreviewFilesProvider({
  files,
  children,
}: {
  files: PreviewFile[];
  children: ReactNode;
}) {
  return (
    <HtmlPreviewFilesContext.Provider value={files}>
      {children}
    </HtmlPreviewFilesContext.Provider>
  );
}

export function useHtmlPreviewFiles(): PreviewFile[] {
  return useContext(HtmlPreviewFilesContext);
}
