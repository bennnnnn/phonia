/**
 * The document URL react-native-webview gives inline `source={{ html }}`
 * when no `baseUrl` is passed (no preview passes one). iOS:
 * RNCWebViewImpl.m `visitSource` falls back to about:blank. Android:
 * RNCWebViewManagerImpl.kt passes "" to loadDataWithBaseURL, which WebView
 * reads as about:blank.
 */
export const INLINE_DOCUMENT_URL = "about:blank";

/**
 * A server on the phone itself (a dev server, another app's local server) and
 * hosts dressed up as one. A preview never loads any of these, in any build.
 */
export const LOOPBACK_URLS = [
  // This app's own inline `baseUrl` until 1bac067bc; nothing passes it now.
  "https://localhost/",
  "https://localhost",
  "http://localhost/",
  "HTTPS://LOCALHOST/",
  "https://localhost:8080/",
  "http://localhost:8081/index.bundle?platform=ios",
  "https://localhost/evil",
  "https://localhost/?v=1",
  "http://127.0.0.1/",
  "http://127.0.0.1:3000/x",
  "https://127.0.0.1:8443/",
  "http://127.1/",
  "http://0.0.0.0:8081/",
  "http://[::1]:8080/",
  "http://localhost.evil.com/",
  "https://localhost@evil.com/",
  "https://evil.com@localhost/",
  "http://user:pass@127.0.0.1:3000/",
];
