import type { SearchSource } from "@/lib/assistantMarkdown";

export function SourcesList({ sources }: { sources: SearchSource[] }) {
  if (sources.length === 0) return null;
  return (
    <div className="sources">
      <div className="sources-label">Sources</div>
      <ul>
        {sources.map((source, index) => {
          const label = source.title || source.url;
          return (
            <li key={`${source.url}-${index}`}>
              {source.url ? (
                <a href={source.url} target="_blank" rel="noopener noreferrer">
                  {label}
                </a>
              ) : (
                label
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
