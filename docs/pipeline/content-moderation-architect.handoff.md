# Architect Handoff: Content Moderation

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## What Was Designed

A backend-only content moderation system that integrates into the existing chat pipeline (`ChatService.validate_send_message()`). It provides four layers of protection: message length enforcement, prompt injection detection via heuristic regex, content safety classification via Claude Haiku, and abuse rate detection with escalating temporary blocks. The therapist character receives additional crisis-aware system prompt augmentation.

## Key Decisions

- **Fail-open on classifier errors**: If Claude Haiku is unreachable, messages are allowed through. Rationale: Ember is a personal companion, not a public forum. Anthropic's built-in Claude safety layer provides a second defense even when the classifier is down. Over-blocking harms user trust more than occasional missed moderation.
- **Prompt injection: detect but do not block**: Injection attempts are flagged and an injection-resistant preamble is prepended to the system prompt, but the message is still sent to the LLM. Rationale: false positive rate for regex-based injection detection is high. Blocking would frustrate legitimate users. The preamble approach neutralizes most attacks without rejecting the message.
- **Haiku classification runs before Mem0/LLM calls**: The classification call adds latency (~500ms) but runs in parallel with the abuse state DB check. Blocked messages never reach the expensive Mem0 search or Sonnet streaming call, saving resources.
- **No Mem0 storage of moderation events**: Violations are stored in PostgreSQL only. Characters should not "remember" that a user sent harmful content, as this creates a negative feedback loop in the companion relationship.
- **Therapist crisis augmentation is per-message, not persistent**: The crisis resource system prompt text is injected only for the message where crisis is detected. It does not alter the stored `system_prompt` column.
- **Backend-only scope**: No new API endpoints, no iOS/Android screen changes. Moderation errors surface through existing 400/403 error handling that mobile clients already implement.

## Spec Location

`shared/feature-specs/content-moderation.md`

## Assumptions Made

- Anthropic Claude Haiku's `complete_fast()` can reliably classify content safety in <500ms.
- The existing `max_tokens=2048` parameter on the Sonnet streaming call effectively caps AI response length at approximately 8000 characters, satisfying the response length requirement without explicit character counting.
- Mobile clients already handle 400 and 403 error responses with user-facing messages from the `detail` field.

## Dependencies

- Requires: P01-06 (chat-streaming) -- must exist for the moderation service to hook into.
- Blocks: backend-dev (implements), backend-tester (tests).

## Next Steps

backend-dev should read the spec and implement. No iOS or Android work is needed for this backend-only feature.
