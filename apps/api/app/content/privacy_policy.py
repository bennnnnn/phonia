"""Hosted privacy policy (App Store / Play Console privacy URL).

Every claim here is checked against the code: the external services in
``app/gateways/``, what the phone sends (``apps/mobile/lib/deviceLocation.ts``,
Sentry, push), and the retention facts in SECURITY.md. Change the text together
with the code it describes, and bump ``LEGAL_EFFECTIVE_DATE``.
"""

# Legal prose is one paragraph or bullet per line.
# ruff: noqa: E501

from __future__ import annotations

from app.content.legal import LEGAL_EFFECTIVE_DATE, contact_markdown

_PRIVACY_POLICY_MD = """# Privacy Policy

**Effective date: {effective_date}**

This policy explains what Recall collects, who receives it, how long it is kept, and how you control it. Recall is an AI chat app: to answer you, parts of your data must be sent to the outside AI and search services named below. Nothing is sent to them until you agree. In the phone app, the sign-in page says this next to its sign-in buttons, and signing in is your agreement; the web app asks after you sign in.

## What We Collect

- **Account information**: Your name, email address and profile picture from Google or Apple Sign-In, and which of the two you use.
- **Profile and settings**: What you add in Settings, such as a display name or photo, age, country, job, custom instructions, language, time zone and preferences.
- **Conversations**: Messages you send, responses from the AI, chat titles, summaries of long chats, and your thumbs-up/thumbs-down feedback. Live talk turns are saved as text in the chat; the audio itself is not stored.
- **Learned facts**: Information Recall saves to personalize your experience (preferences, projects, facts you share). You can see, edit, mute or delete each one on the Memory screen, or turn memory off.
- **Reminders**: To-dos and reminders you create or confirm.
- **Files and photos**: Images and documents you attach, AI images you create, the text read from them, and numeric search indexes (embeddings) of your messages, memory and files that let Recall find relevant context.
- **Scanned problems**: A photo you take or pick in the scanner (math, physics and chemistry) is sent to Recall's server to read the problem, and the text read from it comes back to you to check. Recall does not keep that photo; the problem you then send is saved like any other message. If you choose Send photo instead, or scan a biology problem, the photo is attached to the chat and kept like any other photo.
- **Location (optional)**: Off until you turn on Use current location (Settings → Data controls), or allow location when you ask a nearby question, which turns that setting on. Your phone's operating system (Apple or Google) turns the position into a place name, and Recall saves that city, region and country (or rounded coordinates when no name is found). For a nearby or "where am I" question, the phone also sends its precise coordinates with that one message.
- **Device and session data**: The device name or model and platform of each signed-in session (listed in Settings → Security), your time zone, and, if you allow notifications, a push notification token with an id for this app install.
- **Usage data**: Token and feature counts for daily quota tracking and a limited set of product events such as paywall views, purchase outcomes, notification permission results and how quickly replies start. Product events do not include prompts, message text, search queries, or attachment names.
- **Purchases**: Your plan and subscription status, from RevenueCat. Apple or Google handle payment; Recall never sees your card details.

## How We Use Your Data

- To provide personalized AI responses based on what you've shared, using your recent messages, relevant memory, files and earlier chats.
- To write chat titles, save memory, suggest follow-up questions and keep your reminders.
- To improve response quality via thumbs-up/thumbs-down feedback.
- To enforce daily usage limits and prevent abuse.
- To send the reminders you turn on (push or email), a welcome email and purchase receipts.
- To understand product reliability, feature adoption, and subscription conversion, and to fix crashes and errors.

We do not sell your personal data and do not use it for advertising.

## AI Processing and Other Services That Receive Your Data

- **AI model providers, through OpenRouter**: Your messages, recent chat history, relevant saved memory and reminders, profile details that help the answer (your name and, when relevant, email address, age, country, job, custom instructions, time zone and location), photos and files you attach with the text read from them, photos you scan in the scanner (math, physics and chemistry), and web search results. OpenRouter forwards each request to a company that runs the chosen model: the model's maker (currently Anthropic, OpenAI, DeepSeek, Alibaba's Qwen, Z.ai, and Black Forest Labs for AI images) or another hosting provider OpenRouter works with. Background work uses the same route: chat titles, memory, follow-up questions, reading photos and scanned PDFs, and the search indexes described above.
- **OpenAI, for voice**: When you use voice input, read aloud or live talk, your recorded audio and the text to be read go to OpenAI. During live talk your phone connects to OpenAI directly with a short-lived key, and OpenAI also receives that conversation's instructions, which include recent messages, relevant memory, your custom instructions and upcoming reminders.
- **Mathpix, for math photos**: Photos of math problems you scan, or send asking for a solution, go to Mathpix to read the math. Recall asks Mathpix not to keep them to improve its service.
- **Tavily, for web search and photo lookups**: Search words Recall writes from your message, which can include your city or, for nearby questions, your coordinates. If Tavily has no answer or your daily search allowance is used up, our server sends the same search words to public search engines (such as DuckDuckGo, Bing or Google) instead. You can turn web search and photo lookups off in Settings → Data controls.
- **PubChem, for chemistry**: The names or structures of chemicals in a chemistry question, to look up their properties. No account details are sent.

Each of these services handles the data under its own terms and privacy policy. Avoid sharing anything you would not want them to process.

## Service Providers

- **OpenRouter** routes AI requests to the model providers above.
- **OpenAI** provides voice input, read aloud and live talk.
- **Mathpix** reads math in photos.
- **Tavily** provides web search and reference photos; public search engines are the backup.
- **PubChem** (U.S. National Center for Biotechnology Information) answers chemistry lookups.
- **Google** provides Google Sign-In, the small site icons shown beside web sources, and place names for your location on Android.
- **Apple** provides Sign in with Apple and place names for your location on iPhone.
- **RevenueCat**, with the App Store and Google Play, handles subscriptions and purchase status.
- **Sentry** receives crash and error reports.
- **Cloudflare R2** stores your files and photos.
- **Neon** hosts the database.
- **Upstash** hosts the cache, usage counters and background job queue.
- **Fly.io** hosts Recall's servers.
- **Resend** delivers email.
- **Expo** delivers push notifications (through Apple's and Google's push services) and app updates.

Your phone talks to some of these directly: Google or Apple when you sign in, RevenueCat and the store when you buy, Expo for notifications and updates, OpenAI during live talk, Sentry for crash reports, Google for site icons, and public code hosts when you run an HTML preview that loads their scripts.

## Data Storage

Your account data, conversations, memories, and limited product-event metadata are stored in a secure PostgreSQL database run by Neon; files are stored in Cloudflare R2. Connections to Recall and between its services are encrypted. Sign-in tokens on your phone are kept in the device's secure storage, and the phone keeps a copy of recent chats so they open quickly; signing out clears that copy. Our providers may process data in the United States and other countries.

Crash and error reports hold technical details (device type, operating system, app version and where the error happened). Recall sends them without request bodies or program variables, so message text and sign-in tokens stay out of them.

## How Long We Keep Data

- **Your account content** (profile, chats, memory, reminders, files, usage counts and product events) is kept until you delete it or delete your account.
- **Unfinished uploads**, and temporary copies made while sending a file, are deleted automatically within about 1 to 24 hours.
- **Sign-in sessions** last up to 30 days without use; signing out, signing out everywhere or removing a device ends them at once.
- **Short-lived caches** (such as search results, memory and the home screen) expire on their own within an hour.
- **After you delete your account**, see [what is kept and for how long](/legal/delete-account).
- **Crash reports** are kept by Sentry for its retention period.

## Your Rights

- **Export**: Download a portable JSON copy of your account data from Settings. The file includes an `export_limits` object describing operational limits.
- **Delete account**: Permanently delete your account and all associated data from Settings → Data controls → Delete your account. This is irreversible. You can also [request deletion without the app](/legal/delete-account).
- **Delete memories**: Remove individual learned facts from the Memory screen, or turn memory off.
- **Delete chats**: Delete one chat or clear all of them.
- **Turn things off**: Web search, location, notifications and email reminders each have a switch in Settings.
- **AI processing**: Recall cannot answer without the AI services above. You can withdraw your agreement in the phone app (Settings → Data controls); Recall then cannot chat, use your voice or read photos until you agree again. To stop for good, delete your account.

Depending on where you live, you may also have the right to access, correct or delete your data, or to object to how it is used. Contact us to make a request.

## Children's Privacy

Recall is not intended for users under 13. We do not knowingly collect data from children.

## Changes

We may update this policy. Material changes will be surfaced in the app. Check this page for the latest version; the effective date above shows when it last changed.

## Contact

If you have questions about this policy or your data, {contact}."""


def privacy_policy_markdown(support_email: str) -> str:
    return _PRIVACY_POLICY_MD.format(
        effective_date=LEGAL_EFFECTIVE_DATE,
        contact=contact_markdown(support_email),
    )
