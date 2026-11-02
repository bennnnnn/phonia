"use strict";

/**
 * The @sentry/conventions/attributes names the bundled Sentry SDK reads, with their values.
 *
 * The package itself is 745 attribute names plus a registry of every attribute's type and
 * description (about 300 KB in the bundle) that nothing in the app reads. metro.config.js
 * serves this file in its place. lib/__tests__/metroBundle.test.ts compares it with the
 * installed package and fails, naming the lines to add, when a Sentry upgrade imports a
 * name this file lacks or changes a value.
 */
module.exports = {
  GEN_AI_EMBEDDINGS_INPUT: "gen_ai.embeddings.input",
  GEN_AI_INPUT_MESSAGES: "gen_ai.input.messages",
  GEN_AI_OPERATION_NAME: "gen_ai.operation.name",
  GEN_AI_PROVIDER_NAME: "gen_ai.provider.name",
  GEN_AI_REQUEST_FREQUENCY_PENALTY: "gen_ai.request.frequency_penalty",
  GEN_AI_REQUEST_MAX_TOKENS: "gen_ai.request.max_tokens",
  GEN_AI_REQUEST_MODEL: "gen_ai.request.model",
  GEN_AI_REQUEST_PRESENCE_PENALTY: "gen_ai.request.presence_penalty",
  GEN_AI_REQUEST_TEMPERATURE: "gen_ai.request.temperature",
  GEN_AI_REQUEST_TOP_K: "gen_ai.request.top_k",
  GEN_AI_REQUEST_TOP_P: "gen_ai.request.top_p",
  GEN_AI_SYSTEM_INSTRUCTIONS: "gen_ai.system_instructions",
  GRAPHQL_DOCUMENT: "graphql.document",
  HTTP_REQUEST_HEADER_KEY_BASE: "http.request.header",
  HTTP_URL: "http.url",
  PARAMS_KEY_BASE: "params",
  SENTRY_OP: "sentry.op",
  SENTRY_SDK_NAME: "sentry.sdk.name",
  SENTRY_SDK_VERSION: "sentry.sdk.version",
  SENTRY_SEGMENT_ID: "sentry.segment.id",
  SENTRY_SEGMENT_NAME: "sentry.segment.name",
  SENTRY_TRACE_LIFECYCLE: "sentry.trace_lifecycle",
  SENTRY_TRANSACTION: "sentry.transaction",
  URL_FULL: "url.full",
  URL_PATH: "url.path",
  URL_PATH_PARAMETER_KEY_BASE: "url.path.parameter",
  URL_QUERY: "url.query",
  URL_TEMPLATE: "url.template",
  USER_AGENT_ORIGINAL: "user_agent.original",
};
