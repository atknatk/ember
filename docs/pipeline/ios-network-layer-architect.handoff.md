# Architect Handoff: iOS Network Layer

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## What Was Designed

A production-ready iOS networking layer replacing the P03-01 stubs. The spec defines a generic `APIClient` with `request<T>`, `requestVoid`, and `streamSSE` methods; an `APIEndpoint` enum for type-safe endpoint routing; an `SSEClient` with `SSEDelegate` that parses the backend's five SSE event types (chunk, action, done, error, moderation) into a typed `SSEEvent` enum yielded via `AsyncThrowingStream`; and automatic 401 retry logic that calls `AuthServiceProtocol.refreshToken()` then retries once.

## Key Decisions

- Generic `request<T>` / `requestVoid` / `streamSSE` methods on `APIClientProtocol` instead of per-endpoint methods. New features add cases to `APIEndpoint` enum without touching the protocol.
- `SSEEvent` typed enum with `payloadJSON: Data` (not `[String: Any]`) for `Sendable` safety.
- No automatic 401 retry for SSE streams -- the stream yields an error and the ViewModel handles re-auth. Only standard HTTP requests retry.
- `refreshToken()` added to `AuthServiceProtocol` (stubbed) to support the retry flow.
- `MockURLProtocol` for network testing, not URLSession mocking.

## Spec Location

`shared/feature-specs/ios-network-layer.md`

## Assumptions Made

- `AuthService.refreshToken()` will be implemented in the Cognito auth feature. Until then, it throws `AuthError.notImplemented`, which means the 401 retry path effectively always throws `APIError.unauthorized`.
- The backend always returns SSE for `POST /characters/:id/messages` (confirmed by reading `backend/app/routes/chat.py`).
- The SSE event format matches `backend/app/schemas/chat.py`: five event types (chunk, action, done, error, moderation) with `data: {json}\n\n` framing.

## Dependencies

- Requires: P03-01 (ios-scaffold) -- provides the stub files this feature modifies.
- Blocks: all subsequent iOS features that make API calls (character list, chat, memories, profile, auth screens).

## Next Steps

ios-dev should read the spec and implement. ios-tester follows after implementation is complete.
