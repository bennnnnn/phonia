import type { PlanFeature, PlanId } from "@/lib/plan";
import type { SearchSource } from "@/lib/searchSources";

export type { SearchSource };

/** Voices both read-aloud and live talk speak (the server's UserVoice). */
export type UserVoice =
  | "marin"
  | "cedar"
  | "alloy"
  | "ash"
  | "ballad"
  | "coral"
  | "echo"
  | "sage"
  | "shimmer"
  | "verse";

export type User = {
  id: string;
  email: string;
  name: string | null;
  avatar_url: string | null;
  default_model: string;
  plan: PlanId;
  /** What the plan includes (display only; the server checks every request). */
  features?: PlanFeature[];
  enabled_models: string[] | null;
  /** Three follow-up questions under a reply; on unless the user turned it off. */
  follow_up_suggestions_enabled?: boolean;
  /** Web search and photo lookups (Settings → Data controls); on unless turned off. */
  web_search_enabled?: boolean;
  /** When the account agreed to what goes to outside AI services; null until it does.
   * Absent only from an older server, which the consent gate lets through. */
  ai_data_consent_at?: string | null;
  response_tone: string;
  /** How many emoji replies use: "off", "some" (the default) or "more". */
  emoji_use?: string;
  memory_enabled: boolean;
  memory_include_sensitive?: boolean;
  push_notifications_enabled: boolean;
  /** Each push kind's own switch, under the master one. */
  push_reminders_enabled?: boolean;
  /** Read-aloud and live talk voice; null is the server default. */
  tts_voice?: UserVoice | null;
  email_reminders_enabled?: boolean;
  /** False when the server cannot send email (no provider set up): hide the switch. */
  email_reminders_available?: boolean;
  reminder_lead_minutes: number;
  locale: string;
  timezone: string;
  location: string | null;
  location_enabled: boolean;
  custom_instructions: string | null;
  age: number | null;
  country: string | null;
  job: string | null;
  created_at: string;
  sign_in_provider?: "google" | "apple" | "dev";
  /** Signs in with Apple (alone or beside Google); deleting asks Apple once more. */
  apple_linked?: boolean;
  quiet_hours_enabled?: boolean;
  quiet_hours_start_minute?: number;
  quiet_hours_end_minute?: number;
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

/** A page of a list: pass `next_cursor` back as `cursor` for the next; null after the last. */
export type Page<T> = { items: T[]; next_cursor: string | null };

export type Feedback = "up" | "down" | null;

export type MessagePage = {
  messages: Message[];
  /** Older messages precede the page. */
  has_more: boolean;
  /** Newer messages follow it: a page read `around` or `after` a message. */
  has_more_after?: boolean;
};

export type Message = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  model: string | null;
  feedback?: Feedback;
  /** Related subject questions for the latest reply. Tap sends the string. */
  related_prompts?: string[] | null;
  search_sources?: SearchSource[];
  local_image_uri?: string | null;
  local_file_uri?: string | null;
  local_file_name?: string | null;
  local_file_content_type?: string | null;
  /** Client-only FlashList key — stable while `id` changes streaming → persisted. */
  renderKey?: string;
  /** Client-only: image generation stopped or failed (inline card + retry). */
  image_gen_failure?: "canceled" | "failed";
  image_gen_error?: string;
  /** Client-only: refused for a reason a retry meets again (the day's cap, content rules): no Retry. */
  image_gen_refused?: boolean;
  /** Client-only: stream was stopped or the provider died after tokens started. */
  generationStopped?: boolean;
  /** Saved with the reply: it did not finish (Stop, or cut off). Null when it did. */
  completion?: "interrupted" | "user_stop" | null;
  /** Client-only: the reply came whole (`stream_end`), then the server failed to save it. */
  replyNotSaved?: boolean;
  created_at: string;
};

export type Memory = {
  id: string;
  type: string;
  /** The memory document this fact belongs to (profile, tech-stack, area:recall, …). */
  topic?: string;
  text: string;
  confidence: number | null;
  status?: "active" | "muted" | "superseded";
  sensitivity?: string | null;
  last_confirmed_at?: string | null;
  source_chat_id?: string | null;
  source_chat_title?: string | null;
  created_at: string;
  updated_at: string;
};

export const RECURRENCE_RULES = ["daily", "weekdays", "weekly", "monthly"] as const;
export type RecurrenceRule = (typeof RECURRENCE_RULES)[number];

export type Todo = {
  id: string;
  content: string;
  topic: string;
  checked: boolean;
  due_at: string | null;
  recurrence_rule?: RecurrenceRule | null;
  sort_order: number | null;
  chat_id: string | null;
  created_at: string;
  updated_at: string;
  /** When its reminder goes out, worked out by the server (the lead time, after quiet hours);
   * push sends then, and the phone's own alert is scheduled at it as is. Null: none. */
  notify_at: string | null;
};

export type SearchResult = {
  match_type: "message" | "title";
  message_id: string | null;
  chat_id: string;
  chat_title: string | null;
  content: string;
  role: string;
  created_at: string;
  /** The hit is in an archived chat. */
  archived?: boolean;
};

export type HomeUrgentTodo = {
  id: string;
  content: string;
  topic: string;
  due_at: string;
  minutes_until: number;
};

export type ChatList = {
  pinned: Chat[];
  today: Chat[];
  yesterday: Chat[];
  last_7_days: Chat[];
  this_month: Chat[];
  older: Chat[];
  archived: Chat[];
  /** Older dated chats follow: read them with `cursor`. Absent or null: none. */
  next_cursor?: string | null;
  /** More archived chats than `archived` holds: GET /chats/archived reads on. */
  archived_next_cursor?: string | null;
};

export type Usage = {
  date: string;
  input_tokens: number;
  output_tokens: number;
  daily_limit: number;
  used_tokens?: number;
  remaining: number;
  context_token_budget?: number;
  recent_message_window?: number;
};

/** One entry of GET /models. The server also sends prices and quota
 * multipliers; the phone neither shows nor keeps them, so it leaves them out. */
export type ModelInfo = {
  id: string;
  label: string;
  description: string;
  tier: string;
  plan_access: "free" | "pro";
  available: boolean;
  healthy?: boolean;
  latency_p50_ms?: number | null;
  health_samples?: number;
};

export type AuthResult = {
  access_token: string;
  refresh_token: string;
  user: User;
};

export type AuthSession = {
  id: string;
  device_label: string | null;
  platform: string | null;
  created_at: string | null;
  last_seen_at: string | null;
  current: boolean;
};
