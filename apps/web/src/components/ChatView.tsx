import { useEffect, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useChat } from "@/hooks/useChat";
import { getAccessToken } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { MessageBubble } from "@/components/MessageBubble";
import { Composer } from "@/components/Composer";

export function ChatView() {
  const { chatId } = useParams<{ chatId: string }>();
  const navigate = useNavigate();
  const { signOut } = useAuth();
  const accessToken = getAccessToken();
  const { messages, loading, streaming, statusPhase, error, send, stop, regenerate } =
    useChat(accessToken ?? "", chatId ?? null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new content.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (!accessToken) {
    navigate("/");
    return null;
  }

  const hasAssistant = messages.some((m) => m.role === "assistant");

  return (
    <div className="chat-view">
      <header>
        <button className="back" onClick={() => navigate("/chats")}>←</button>
        <h1>{messages.length > 0 ? "Chat" : "New chat"}</h1>
        <button onClick={() => signOut().then(() => navigate("/"))}>Sign out</button>
      </header>
      {error && <p className="error">{error}</p>}
      <div className="messages">
        {loading && messages.length === 0 ? (
          <p className="muted">Loading…</p>
        ) : messages.length === 0 ? (
          <p className="muted">Say hello to start.</p>
        ) : (
          messages.map((m) => <MessageBubble key={m.id} message={m} />)
        )}
        <div ref={bottomRef} />
      </div>
      <Composer
        streaming={streaming}
        statusPhase={statusPhase}
        onSend={(t) => send(t)}
        onStop={stop}
        onRegenerate={() => regenerate()}
        canRegenerate={hasAssistant && !streaming}
      />
    </div>
  );
}
