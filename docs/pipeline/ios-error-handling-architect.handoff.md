# Architect Handoff: iOS Error Handling

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## Feature
- **ID**: P03-11
- **Name**: ios-error-handling
- **Layer**: ios

## Scope
Centralized error handling for all iOS screens: EmberError enum, ErrorBannerView, NetworkMonitor, OfflineBannerView, RetryHelper, and updates to all existing ViewModels and Views.

## Spec Location
`shared/feature-specs/ios-error-handling.md`

## Key Decisions
- Non-blocking error banners instead of `.alert()` modals
- `@Observable` NetworkMonitor using NWPathMonitor
- EmberError factory pattern to map all error types
- Exponential backoff retry helper as standalone utility
- Backward-compatible: keeps `errorMessage: String?` alongside `currentError: EmberError?`
