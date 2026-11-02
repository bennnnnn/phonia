// Types copied from apps/mobile/lib/api/types.ts (slice 1 subset).
// A shared packages/api-types is a later slice — copy for now so the web
// client is standalone and the mobile network boundary stays untouched.

export type User = {
  id: string;
  email: string;
  name: string | null;
  avatar_url: string | null;
  default_model: string;
  plan: "free" | "pro";
  response_style: string;
  response_tone: string;
  memory_enabled: boolean;
  locale: string;
  timezone: string;
  /** When the account agreed to what goes to outside AI services; null until it does. */
  ai_data_consent_at?: string | null;
  created_at: string;
};

export type Chat = {
  id: string;
  title: string | null;
  model: string;
  pinned: boolean;
  archived?: boolean;
  created_at: string;
  updated_at: string;
};

type Feedback = "up" | "down" | null;

export type SearchSource = {
  title: string;
  url: string;
  snippet?: string;
};

export type Message = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  model: string | null;
  feedback?: Feedback;
  search_sources?: SearchSource[];
  created_at: string;
};

export type MessagePage = {
  messages: Message[];
  has_more: boolean;
};

export type ChatList = {
  pinned: Chat[];
  today: Chat[];
  yesterday: Chat[];
  last_7_days: Chat[];
  this_month: Chat[];
  older: Chat[];
  archived: Chat[];
};

export type AuthResult = {
  access_token: string;
  refresh_token?: string;
  csrf_token?: string | null;
  user: User;
};

// SSE / WS stream event types (shared shape — see apps/api/app/services/chat/
// stream_events.py). The web client consumes these over SSE.
export type StreamEvent =
  | { type: "start" }
  | { type: "token"; content: string }
  | { type: "status"; phase: string; detail?: string }
  | { type: "reasoning"; content: string }
  | { type: "stream_end"; resolved_model?: string }
  | {
      type: "done";
      message_id?: string;
      final_content?: string;
      search_sources?: string;
      resolved_model?: string;
    }
  | { type: "error"; code?: string; message: string };
