# Architect Handoff: doc-code-sync

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## What Was Designed

A comprehensive audit of all documentation-code contradictions across the Ember backend, producing a catalog of 28 contradiction entries (26 real contradictions, 2 confirmed-consistent). Each entry specifies which source is authoritative (code wins in all cases where the feature is already working), the exact fix required, and which doc files to modify. A CI check script is also designed to mechanically prevent the most common drift patterns from recurring.

## Key Decisions

- Code is the authority in all cases -- no docs described behavior that should have been implemented but was not; instead, docs failed to track implementation changes.
- The CI script (`scripts/check_doc_code_sync.py`) checks mechanically verifiable assertions only (file existence, import paths, class names, config field coverage). It does not attempt to parse prose descriptions in docs.
- The CI script produces warnings (not failures) for config field coverage mismatches, and hard failures for structural contradictions (nonexistent model imports, stale module paths).
- No code logic changes are required. This is purely a documentation + CI tooling task.

## Spec Location

`shared/feature-specs/doc-code-sync.md`

## Assumptions Made

- The mem0 SDK does not provide an `AsyncMemoryClient` class -- confirmed by the actual imports in working code.
- All contradictions found are exhaustive for the docs listed in the required reading list.
- The conversation auto-creation at character creation time (not first message) is the intended behavior.

## Dependencies

- Requires: P01-10 (media-upload) -- all Phase 1 features must be complete so the audit reflects the final state.
- Blocks: No features depend on this, but completing it improves reliability for all future agent sessions.

## Next Steps

backend-dev should read the spec and implement all doc updates and the CI check script. The task is doc-editing and a single Python script -- no service code changes.
