/** The empty chat's greeting, built on the phone: no request, in the phone's language.
 *
 * The greeting came from `GET /home` on every start, return and token rotation; the
 * server's was English only and replaced the translated one (code-health audit NET-10). */

import i18n from "@/lib/i18n";

function partOfDay(now: Date): "morning" | "afternoon" | "evening" | "night" {
  const hour = now.getHours();
  if (hour >= 5 && hour < 12) return "morning";
  if (hour >= 12 && hour < 17) return "afternoon";
  if (hour >= 17 && hour < 22) return "evening";
  return "night";
}

/** "Good morning, Sam": the first word of the account's name, when it has one. */
export function homeGreeting(name: string | null | undefined, now: Date = new Date()): string {
  const first = name?.trim().split(/\s+/)[0];
  const part = partOfDay(now);
  return first
    ? i18n.t(`chat.home.greeting_${part}_name`, { name: first })
    : i18n.t(`chat.home.greeting_${part}`);
}
