import { act, render, screen } from "@testing-library/react-native";

import { LinkPreviewCard } from "@/components/LinkPreviewCard";
import { LinkPreviewTrust } from "@/components/markdown/LinkPreviewTrust";
import { request } from "@/lib/api/client";
import { ApiRequestError } from "@/lib/api/errorBody";
import { clearLinkPreviewCache } from "@/lib/linkPreview";

jest.mock("@/lib/api/client", () => ({ request: jest.fn() }));
jest.mock("@/lib/auth", () => ({ getToken: jest.fn(async () => "token") }));
jest.mock("@/lib/linkSchemePolicy", () => ({ openAllowedUrl: jest.fn() }));

const fetchPreview = request as jest.Mock;
const LINKS = [1, 2, 3, 4].map((n) => `https://site${n}.example/page`);
/** The server lets one user have three previews loading at once (modules/link_preview/service.py). */
const SLOTS = 3;
/** Its busy refusal, with `Retry-After: 8` (modules/link_preview/api.py). */
const BUSY_MS = 8_000;

function reply(links: string[] = LINKS) {
  return (
    <LinkPreviewTrust userText={`compare ${LINKS.join(" ")}`}>
      {links.map((url, index) => (
        <LinkPreviewCard key={`${index}-${url}`} url={url} />
      ))}
    </LinkPreviewTrust>
  );
}

/**
 * The phone asks three at a time, so its own previews never fill the server's slots; a busy
 * refusal is another install of the account holding them. By default the fourth link's first
 * ask meets one.
 */
function firstAskOfFourthBusy(url: string): boolean {
  return url === LINKS[3] && asked(url) === 1;
}

/** The server: three previews load at once, and `isBusy` says which asks it refuses busy. */
function serveWithSlots(isBusy: (url: string, open: number) => boolean = firstAskOfFourthBusy) {
  let open = 0;
  fetchPreview.mockImplementation(async (path: string) => {
    const url = decodeURIComponent(path.split("url=")[1]);
    if (open >= SLOTS || isBusy(url, open)) throw busy();
    open += 1;
    await Promise.resolve();
    open -= 1;
    return { url, title: `Title of ${url}`, description: null, domain: new URL(url).host };
  });
}

function busy(): ApiRequestError {
  const body = JSON.stringify({ detail: { code: "link_preview_busy", message: "Too many previews loading." } });
  return new ApiRequestError(429, body, BUSY_MS);
}

/** Requests for one link. */
function asked(url: string): number {
  return fetchPreview.mock.calls.filter(([path]) => decodeURIComponent(String(path).split("url=")[1]) === url).length;
}

async function wait(ms: number) {
  await act(async () => {
    await jest.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  jest.useFakeTimers();
  clearLinkPreviewCache();
  fetchPreview.mockReset();
});

afterEach(() => {
  jest.useRealTimers();
});

it("shows a 4-link reply's busy card again after the server's wait, asking once and not before", async () => {
  serveWithSlots();

  const first = await render(reply());
  expect(await screen.findAllByText(/^Title of /)).toHaveLength(SLOTS);
  expect(screen.getByRole("link", { name: LINKS[3] })).toBeOnTheScreen();
  expect(fetchPreview).toHaveBeenCalledTimes(4);
  await act(async () => first.unmount());

  // The reply comes back into view before the wait is over: no request at all.
  jest.setSystemTime(Date.now() + BUSY_MS - 1);
  const early = await render(reply());
  expect(screen.getAllByText(/^Title of /)).toHaveLength(SLOTS);
  expect(screen.getByRole("link", { name: LINKS[3] })).toBeOnTheScreen();
  expect(fetchPreview).toHaveBeenCalledTimes(4);
  await act(async () => early.unmount());

  // After it: the busy link alone is asked for, once, and its card shows.
  jest.setSystemTime(Date.now() + 1);
  const later = await render(reply());
  expect(await screen.findByText(`Title of ${LINKS[3]}`)).toBeOnTheScreen();
  expect(screen.getAllByText(/^Title of /)).toHaveLength(4);
  expect(fetchPreview).toHaveBeenCalledTimes(5);
  await act(async () => later.unmount());

  await render(reply());
  expect(screen.getAllByText(/^Title of /)).toHaveLength(4);
  expect(fetchPreview).toHaveBeenCalledTimes(5);
});

it("turns a busy card that stays on screen into its preview after the wait, with one more request", async () => {
  serveWithSlots();
  await render(reply());
  await wait(0);
  expect(screen.getAllByText(/^Title of /)).toHaveLength(SLOTS);
  expect(screen.getByRole("link", { name: LINKS[3] })).toBeOnTheScreen();
  expect(fetchPreview).toHaveBeenCalledTimes(4);

  await wait(BUSY_MS - 1);
  expect(screen.getByRole("link", { name: LINKS[3] })).toBeOnTheScreen();
  expect(fetchPreview).toHaveBeenCalledTimes(4);

  await wait(1);
  expect(screen.getByText(`Title of ${LINKS[3]}`)).toBeOnTheScreen();
  expect(screen.getAllByText(/^Title of /)).toHaveLength(4);
  expect(fetchPreview).toHaveBeenCalledTimes(5);

  await wait(10 * 60_000);
  expect(fetchPreview).toHaveBeenCalledTimes(5);
});

it("lets two cards of the same busy link share the first request and the retry", async () => {
  serveWithSlots();
  await render(reply([...LINKS, LINKS[3]]));
  await wait(0);
  expect(screen.getAllByRole("link", { name: LINKS[3] })).toHaveLength(2);
  expect(fetchPreview).toHaveBeenCalledTimes(4);

  await wait(BUSY_MS);
  expect(screen.getAllByText(`Title of ${LINKS[3]}`)).toHaveLength(2);
  expect(fetchPreview).toHaveBeenCalledTimes(5);
});

it("asks nothing for a busy card that left the screen", async () => {
  serveWithSlots();
  const view = await render(reply());
  await wait(0);
  expect(fetchPreview).toHaveBeenCalledTimes(4);
  await act(async () => view.unmount());

  await wait(10 * 60_000);
  expect(fetchPreview).toHaveBeenCalledTimes(4);
});

it("asks a card refused busy again at most twice more, then leaves it the plain link", async () => {
  serveWithSlots((url) => url === LINKS[3]);
  await render(reply());
  await wait(0);
  expect(asked(LINKS[3])).toBe(1);

  await wait(BUSY_MS);
  expect(asked(LINKS[3])).toBe(2);
  await wait(BUSY_MS);
  expect(asked(LINKS[3])).toBe(3);

  await wait(10 * 60_000);
  expect(asked(LINKS[3])).toBe(3);
  expect(screen.getByRole("link", { name: LINKS[3] })).toBeOnTheScreen();
  expect(fetchPreview).toHaveBeenCalledTimes(6);
});

it("never asks again for a preview that really failed while its card is shown", async () => {
  fetchPreview.mockImplementation(async (path: string) => {
    const url = decodeURIComponent(path.split("url=")[1]);
    if (url === LINKS[3]) throw new ApiRequestError(404, JSON.stringify({ detail: "Not found" }));
    return { url, title: `Title of ${url}`, description: null, domain: new URL(url).host };
  });
  await render(reply());
  await wait(0);
  expect(screen.getByRole("link", { name: LINKS[3] })).toBeOnTheScreen();

  await wait(10 * 60_000);
  expect(asked(LINKS[3])).toBe(1);
});

it("shows every card of a twelve-link reply with one request each, never refused or rate limited", async () => {
  // The server's 20 a minute (modules/link_preview/api.py): asked all at once, the refusals and
  // their retries spent it, and six links stayed plain for five minutes.
  const many = Array.from({ length: 12 }, (_, n) => `https://many${n}.example/page`);
  let thisMinute = 0;
  serveWithSlots(() => {
    thisMinute += 1;
    return false;
  });
  const serve = fetchPreview.getMockImplementation()!;
  fetchPreview.mockImplementation(async (path: string) => {
    if (thisMinute >= 20) throw new ApiRequestError(429, JSON.stringify({ detail: { code: "rate_limited" } }), 60_000);
    return serve(path);
  });
  await render(
    <LinkPreviewTrust userText={`compare ${many.join(" ")}`}>
      {many.map((url) => (
        <LinkPreviewCard key={url} url={url} />
      ))}
    </LinkPreviewTrust>,
  );
  await wait(0);
  expect(screen.getAllByText(/^Title of /)).toHaveLength(12);
  expect(fetchPreview).toHaveBeenCalledTimes(12);
  expect(thisMinute).toBe(12);
});
