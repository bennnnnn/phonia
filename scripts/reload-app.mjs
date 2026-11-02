#!/usr/bin/env node
// Reload every app connected to Metro, as pressing r in its terminal does.
// Metro relays a message sent on its /message socket to each connected app.
// Exits 1, with a note, when no Metro answered.
//
//   node scripts/reload-app.mjs        (Metro on RCT_METRO_PORT, default 8081)

const port = process.env.RCT_METRO_PORT || "8081";
const url = `ws://127.0.0.1:${port}/message`;

if (typeof WebSocket !== "function") {
  console.log("reload-app: this needs Node 22 or newer; press r in Metro instead.");
  process.exit(1);
}

const socket = new WebSocket(url);
let finished = false;
const finish = (code, message) => {
  // Closing can fire another error event; finish once.
  if (finished) return;
  finished = true;
  if (message) console.log(message);
  process.exit(code);
};
const timer = setTimeout(() => finish(1, "reload-app: Metro did not answer."), 3000);

socket.addEventListener("open", () => {
  socket.send(JSON.stringify({ version: 2, method: "reload" }));
  // Give Metro a moment to relay it before the socket closes.
  setTimeout(() => {
    clearTimeout(timer);
    finish(0);
  }, 300);
});
socket.addEventListener("error", () => {
  clearTimeout(timer);
  finish(1, `reload-app: Metro is not running on :${port}.`);
});
