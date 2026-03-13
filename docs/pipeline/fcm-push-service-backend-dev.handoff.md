# Backend Dev Handoff: FCM Push Service

**Date**: 2026-03-13
**Agent**: backend-dev
**Status**: COMPLETE

## Implemented Files
- `backend/app/routes/notifications.py` -- 2 endpoints (PUT, DELETE)
- `backend/app/schemas/notifications.py` -- 2 schemas (FcmTokenRequest, FcmTokenResponse)
- `backend/app/services/notification_service.py` -- 1 service class, 1 public method (send), 1 private method (_clear_token)
- `backend/app/main.py` -- MODIFIED (registered notifications router, added openapi tag)
- `shared/api-contracts/paths/notifications.yaml` -- OpenAPI path spec for notifications/token
- `shared/api-contracts/ember-api.yaml` -- MODIFIED (added notifications path ref and tag)
- `backend/tests/test_openapi_validation.py` -- MODIFIED (updated path count from 15 to 16)
- `backend/tests/test_openapi_yaml.py` -- MODIFIED (updated endpoint count from 20 to 22, added notifications tag)
- `backend/tests/routes/test_notifications_routes.py` -- 12 route tests
- `backend/tests/services/test_notification_service.py` -- 8 service tests

## Endpoints Implemented
- `PUT /api/v1/notifications/token` -- Register/update FCM device token, returns `{"status": "ok"}`
- `DELETE /api/v1/notifications/token` -- Unregister FCM token, returns 204

## Test Results
- pytest: 2252 passed, 0 failed, 13 skipped
- ruff: clean
- All 20 new tests pass (12 route + 8 service)

## Test Command
```bash
cd backend && python -m pytest tests/routes/test_notifications_routes.py tests/services/test_notification_service.py -v
```

## Known Issues / Deviations from Spec
- None. Implementation matches the spec exactly.

## Notes for Backend Tester
- **Route tests**: Mock `get_current_user` and `get_db` via dependency overrides (see existing pattern in test file)
- **Service tests**: Mock `send_push_notification` at `app.services.notification_service.send_push_notification`
- **Database**: Service tests use a mock AsyncSession; the `execute()` return value needs `scalar_one_or_none()` to return the fcm_token value
- **Edge case**: `NotificationService._clear_token` catches DB exceptions silently (logged). Test #18 covers this -- verify exception does not propagate
- **Idempotency**: Both PUT and DELETE are idempotent by design. PUT with same token returns 200, DELETE when no token exists returns 204
- **No new tables or migrations needed** -- uses existing `profiles.fcm_token` column
- **NotificationService does NOT replace notification_scheduler** -- scheduler continues to call `send_push_notification` directly
