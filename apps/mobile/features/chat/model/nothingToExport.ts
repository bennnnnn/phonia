/**
 * The chat has no text to print, so its PDF would be blank. Its own module: the share
 * sheet and the chat menu recognise it without loading expo-print or KaTeX.
 */
export class NothingToExportError extends Error {
  constructor() {
    super("The chat has no text to export.");
    this.name = "NothingToExportError";
  }
}
