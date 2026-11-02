import { useState } from "react";

export function Composer({
  streaming,
  statusPhase,
  onSend,
  onStop,
  onRegenerate,
  canRegenerate,
}: {
  streaming: boolean;
  statusPhase: string | null;
  onSend: (text: string) => void;
  onStop: () => void;
  onRegenerate: () => void;
  canRegenerate: boolean;
}) {
  const [text, setText] = useState("");
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const t = text.trim();
    if (!t || streaming) return;
    onSend(t);
    setText("");
  };
  return (
    <div className="composer">
      {statusPhase && <div className="status-phase">{statusPhase}…</div>}
      <form onSubmit={submit}>
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Message Recall…"
          disabled={streaming}
        />
        {streaming ? (
          <button type="button" onClick={onStop} className="stop">Stop</button>
        ) : (
          <button type="submit" disabled={!text.trim()}>Send</button>
        )}
        {canRegenerate && !streaming && (
          <button type="button" onClick={onRegenerate} className="regen">Regenerate</button>
        )}
      </form>
    </div>
  );
}
