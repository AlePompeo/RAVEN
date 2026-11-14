<!-- SPDX-License-Identifier: Apache-2.0 -->
# Task 8 report
DONE. EchoLLM (echo-llm), FixtureData (example-data), POST /api/chat (SSE, caps 50 msgs/4000 chars, generic error event), GET /api/data/{id} via cached_fetch (stale -> X-Cache: stale; no cache -> 503 {"detail"} without internals). Terms in docs/terms/. Tests: tests/backend/api/test_chat_data.py (run red first: 9 failed).

## Fix round 1 (Task 8)
manifest timeout_s enforced: data fetch (asyncio.timeout; stale -> 200 X-Cache: stale, no cache -> 504 clean JSON, other errors 503) and chat (total timeout + per-token wait_for; generic event: error). cached_fetch now returns Cached(value, stale). Stream construction wrapped (unsubscribe on failure). registry.create unexpected errors -> 502. "system" role removed from client input. Tests updated/added (red first: new timeout test hung on infinite stream).

## Fix round 2 (Task 8)
chat_events: no timeout context across yields; budget = sum of provider wait times (client backpressure not counted), each wait min(timeout, remaining), provider generator aclosed in finally. Data route: UpstreamTimeout raised only from fetch -> 504; cache TimeoutError -> 503. Tests: slow consumer, stalling producer, normal stream ends [DONE], stronger drip test, cache-timeout. Note: tests/backend/test_contracts.py (other agent, uncommitted) fails in sync check; unrelated.

## Fix round 3 (Task 8)
provider.stream() creation moved inside try (sync raise -> generic error event). CHAT_MAX_STREAM_SECONDS (default 120, validated) wall cap: checked each iteration in chat_events, plus _CappedStreamingResponse (timeout around the response, not yields; cap+1s) that aclose()s the generator for stalled consumers. Tests red first (3 failed).
