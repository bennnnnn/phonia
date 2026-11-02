import { useState } from "react";
import { apiUrl } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";

// Same disclosure as the phone's consent screen (apps/mobile lib/i18n en.json,
// onboarding.consent_*) and the privacy policy (apps/api/app/content/privacy_policy.py).
const ITEMS: readonly { title: string; body: string }[] = [
  {
    title: "Chats and memory",
    body: "Your messages, recent chat history, relevant saved memory and profile details go to AI model providers such as Anthropic, OpenAI, DeepSeek, Qwen and Z.ai, through OpenRouter.",
  },
  {
    title: "Files and photos",
    body: "Photos and files you attach, and the text read from them, go to the same AI providers through OpenRouter.",
  },
  {
    title: "Math photos",
    body: "Photos of math problems you scan or send to be solved are also read by Mathpix.",
  },
  {
    title: "Voice",
    body: "Voice input, read aloud and live talk send your voice and the text being read to OpenAI.",
  },
  {
    title: "Web search",
    body: "Searches and photo lookups send search words based on your message to Tavily, or to public search engines as a backup. You can turn web search off in Settings.",
  },
  {
    title: "Location, only if you turn it on",
    body: "Your city, and for nearby questions your exact position, is used in replies and searches.",
  },
];

/** One-time disclosure of what goes to outside AI and search services, before the first chat. */
export function AiConsent() {
  const { agreeToAiData, signOut } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const agree = async () => {
    setBusy(true);
    setError(null);
    try {
      await agreeToAiData();
    } catch {
      setError("Couldn't save your answer. Try again.");
      setBusy(false);
    }
  };

  return (
    <div className="login">
      <div className="login-card consent-card">
        <h1>Before you start</h1>
        <p className="subtitle">
          Recall answers you with help from outside AI and search services. This is what they
          receive. Nothing goes to them until you agree.
        </p>
        <ul>
          {ITEMS.map((item) => (
            <li key={item.title}>
              <strong>{item.title}.</strong> {item.body}
            </li>
          ))}
        </ul>
        <p className="fine">
          Each service handles this data under its own privacy terms. The{" "}
          <a href={apiUrl("/legal/privacy")} target="_blank" rel="noreferrer">
            privacy policy
          </a>{" "}
          lists every service, what Recall keeps and how to delete it.
        </p>
        <div className="consent-actions">
          <button type="button" onClick={() => void agree()} disabled={busy}>
            Agree and continue
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => void signOut()}
            disabled={busy}
          >
            Not now, sign out
          </button>
        </div>
        {error && <p className="error">{error}</p>}
      </div>
    </div>
  );
}
