import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { chatsApi } from "@/api/chats";
import { getAccessToken } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import type { Chat, ChatList as ChatListData } from "@/api/types";

function flattenChats(list: ChatListData): Chat[] {
  return [
    ...list.pinned,
    ...list.today,
    ...list.yesterday,
    ...list.last_7_days,
    ...list.this_month,
    ...list.older,
  ];
}

export function ChatList() {
  const { signOut } = useAuth();
  const navigate = useNavigate();
  const [chats, setChats] = useState<Chat[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const accessToken = getAccessToken();

  const load = () => {
    if (!accessToken) return;
    setLoading(true);
    chatsApi
      .listChats(accessToken)
      .then((list) => setChats(flattenChats(list)))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  };

  useEffect(load, [accessToken]);

  const newChat = async () => {
    if (!accessToken) return;
    try {
      const chat = await chatsApi.createChat(accessToken, "auto");
      navigate(`/chats/${chat.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create chat");
    }
  };

  return (
    <div className="chat-list">
      <header>
        <h1>Recall</h1>
        <div className="header-actions">
          <button onClick={newChat} className="primary">New chat</button>
          <button onClick={() => signOut().then(() => navigate("/"))}>Sign out</button>
        </div>
      </header>
      {error && <p className="error">{error}</p>}
      {loading ? (
        <p className="muted">Loading…</p>
      ) : chats.length === 0 ? (
        <p className="muted">No chats yet. Start a new one.</p>
      ) : (
        <ul>
          {chats.map((chat) => (
            <li key={chat.id}>
              <Link to={`/chats/${chat.id}`}>
                <span className="title">{chat.title ?? "New chat"}</span>
                <span className="time">
                  {new Date(chat.updated_at).toLocaleDateString()}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
