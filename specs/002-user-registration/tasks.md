---

description: "Task list for feature implementation"

---

# Tasks: Self-Service User Registration

**Input**: Design documents from `specs/002-user-registration/` (plan.md, spec.md)

**Prerequisites**: plan.md, spec.md (no data-model.md/contracts/research.md — content folded into plan.md)

**Tests**: Not explicitly requested in spec.md/plan.md — no dedicated test tasks generated (spec-kit rule: tests are optional, only added when requested). Each phase ends with a manual/independent verification step instead.

**Organization**: Tasks grouped by user story (US1/US2/US3, mapped to spec.md priorities P1/P1/P2) plus a Foundational phase (shared domain/adapter changes) and a Cross-Cutting phase (FR-015, which touches `001`'s admin endpoints, not a `002` user story).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: US1, US2, US3 — omitted for Setup/Foundational/Cross-Cutting/Polish

## Path Conventions

Single project, per plan.md structure: `src/user_api/{domain,application,adapters,config.py}`, `migrations/versions/`.

---

## Phase 1: Setup

**Purpose**: Config surface for the new endpoint group; no new dependencies (plan.md: zero new deps for v1).

- [x] T001 [P] Add `AUTH_REGISTER_RATE_LIMIT` env var (default e.g. `10/60s`) to `src/user_api/config.py`
- [x] T002 [P] Create empty Alembic revision file `migrations/versions/xxxxxxxxxxxx_add_email_verification.py` (`alembic revision -m "add email verification"`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Domain and adapter groundwork shared by all three user stories. **Nothing in Phase 3+ can start until this phase is complete.**

- [x] T003 Add `email_verified_at: datetime | None` to `User` and add new `EmailVerificationToken` dataclass (with `is_valid`) in `src/user_api/domain/entities.py`
- [x] T004 [P] Add `InvalidOrExpiredTokenError` and `ResendCooldownError` to `src/user_api/domain/exceptions.py`
- [x] T005 [P] Add `TokenGenerator` and `EmailSender` Protocols to `src/user_api/domain/ports.py`; add `get_by_email_including_pending(email)` and `mark_email_verified(user_id, when)` to the existing `UserRepository` Port
- [x] T006 Implement migration body in `migrations/versions/xxxxxxxxxxxx_add_email_verification.py`: `ALTER TABLE users ADD COLUMN email_verified_at TIMESTAMPTZ NULL` with backfill `email_verified_at = created_at` for existing rows (ADR-001), `CREATE TABLE email_verification_tokens` (id, user_id, token_hash, created_at, expires_at, used_at)
- [x] T007 [P] Add `email_verified_at` to `UserModel` and new `EmailVerificationTokenModel` in `src/user_api/adapters/outbound/persistence/models.py`
- [x] T008 Implement `get_by_email_including_pending` and `mark_email_verified` on `SqlAlchemyUserRepository` in `src/user_api/adapters/outbound/persistence/` (depends on T005, T007)
- [x] T009 [P] Implement `EmailVerificationTokenRepository` in `src/user_api/adapters/outbound/persistence/token_repository.py`, including `consume_and_verify(token_hash, now) -> UUID | None` (ADR-004 single-transaction token+user write) and `get_latest_for_user(user_id)`
- [x] T010 [P] Implement `SecretsTokenGenerator(TokenGenerator)` using stdlib `secrets.token_urlsafe()` in `src/user_api/adapters/outbound/security/token_generator.py`
- [x] T011 [P] Implement `ConsoleEmailSender(EmailSender)` (logs token/link, no real send — ADR-003) in `src/user_api/adapters/outbound/notifications/console_email_sender.py`
- [x] T012 Create `src/user_api/application/registration_use_cases.py` module with `RegisterUser`, `ConfirmEmail`, `ResendVerificationEmail` dataclass shells wired to the Ports above (bodies filled in Phase 3-5)

**Checkpoint**: Domain, persistence, and adapters ready — US1/US2/US3 can now proceed (US2/US3 still functionally depend on US1 having created data, but are independently *implementable*).

---

## Phase 3: User Story 1 - Cadastro público (Priority: P1) 🎯 MVP

**Goal**: Anonymous visitor registers via `POST /auth/register`; account created `pending`, confirmation token issued and "sent".

**Independent Test**: `POST /auth/register` with valid payload → 202, generic body, no auth required; account not visible as active via `001`'s `GET /users/{id}` until confirmed.

- [x] T013 [US1] Implement `RegisterUser.execute` in `src/user_api/application/registration_use_cases.py`: password policy check, duplicate handling (active → no-op, pending → reissue token only if 60s cooldown elapsed since last token else no-op, new → create + hash + persist), issue token, call `EmailSender`; always return 202-equivalent silently regardless of branch taken (FR-001–FR-006, FR-009, FR-010, FR-013)
- [x] T014 [P] [US1] Add `RegisterRequest` Pydantic schema (reuses `MIN_PASSWORD_LENGTH`) in `src/user_api/adapters/inbound/http/schemas.py`
- [x] T015 [US1] Implement `ip_rate_limiter.py` FastAPI dependency — in-memory sliding-window counter per IP, configurable via `AUTH_REGISTER_RATE_LIMIT` — in `src/user_api/adapters/inbound/http/ip_rate_limiter.py` (FR-014, SC-006, ADR-005)
- [x] T016 [US1] Implement `POST /auth/register` route (no `verify_api_key`) in `src/user_api/adapters/inbound/http/auth_router.py`, wiring `RegisterUser` + `ip_rate_limiter` dependency, always returns 202 with generic body (FR-010)
- [x] T017 [US1] Map `WeakPasswordError` → 422 for the `/auth/*` routes in error handling (reuse/extend `001`'s `error_handlers.py`)

**Checkpoint**: US1 independently functional — registration creates pending accounts and logs a confirmation token via `ConsoleEmailSender`.

---

## Phase 4: User Story 2 - Confirmar email (Priority: P1)

**Goal**: User confirms via `GET /auth/confirm?token=...`; account becomes active.

**Independent Test**: valid, unexpired token → 200 and `email_verified_at` set; token reuse → 400/410.

- [x] T018 [US2] Implement `ConfirmEmail.execute` in `src/user_api/application/registration_use_cases.py` using `EmailVerificationTokenRepository.consume_and_verify` (ADR-004 atomic token+user write) (FR-007, FR-008, FR-011)
- [x] T019 [US2] Implement `GET /auth/confirm` route in `src/user_api/adapters/inbound/http/auth_router.py`
- [x] T020 [US2] Map `InvalidOrExpiredTokenError` → always 400 (generic, per FR-011 — never 410, does not distinguish invalid/expired/used/nonexistent) in error handling

**Checkpoint**: US2 independently functional — confirmation flow activates a pending account created by US1 (or seeded directly via T009's repository in isolation).

---

## Phase 5: User Story 3 - Reenviar confirmação (Priority: P2)

**Goal**: User requests a new confirmation email; old token invalidated implicitly by cooldown/new issuance.

**Independent Test**: pending account + resend → 202, new token issued; second resend <60s → 429; unknown/already-active email → 202 generic (no enumeration).

- [x] T021 [US3] Implement `ResendVerificationEmail.execute` in `src/user_api/application/registration_use_cases.py`: silent-success on unknown/already-verified email, 60s cooldown via `get_latest_for_user`, else issue new token (FR-009, FR-010)
- [x] T022 [P] [US3] Add `ResendRequest` schema in `src/user_api/adapters/inbound/http/schemas.py`
- [x] T023 [US3] Implement `POST /auth/register/resend` route in `src/user_api/adapters/inbound/http/auth_router.py`
- [x] T024 [US3] Map `ResendCooldownError` → 429 in error handling. Documented, accepted exception to FR-010's generic-response rule (spec.md FR-010/SC-001, resolved 2026-07-15): 429 is only reachable when a genuinely pending account exists in active cooldown — this is intentional, not a leak to fix

**Checkpoint**: All three `002` user stories independently functional end-to-end (register → confirm → resend).

---

## Phase 6: Cross-Cutting — `email_verified` on `001` admin endpoints (FR-015, SC-007)

**Purpose**: Not a `002` user story — a required, additive exposure change to `001`'s existing admin API.

- [x] T025 [P] Add `email_verified: bool` field to `UserResponse` schema (derived from `email_verified_at is not None`) in `src/user_api/adapters/inbound/http/schemas.py`
- [x] T026 Map `email_verified` in the `GET /users` and `GET /users/{id}` response construction (no new repository method needed — `email_verified_at` already loaded per plan.md)

---

## Phase 7: Polish & Cross-Cutting Concerns

- [x] T027 [P] Wire `auth_router`, `RegisterUser`, `ConfirmEmail`, `ResendVerificationEmail`, and all new adapters (T008-T011) into the composition root/app factory
- [x] T028 [P] Document `AUTH_REGISTER_RATE_LIMIT` and the `ConsoleEmailSender` dev-only limitation (ADR-003 deploy blocker) in project docs
- [x] T029 Manual smoke test of full flow: register → read logged token → confirm → verify `email_verified: true` via `001`'s `GET /users/{id}` → resend cooldown check (validates SC-001 through SC-007 end-to-end)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on Phase 1 — BLOCKS Phases 3-6
- **US1 (Phase 3)**: depends on Phase 2 only
- **US2 (Phase 4)**: depends on Phase 2; functionally needs a pending account (from US1 or seeded directly) to be *tested* end-to-end, but implementation has no code dependency on Phase 3
- **US3 (Phase 5)**: depends on Phase 2; same relationship to US1 as US2
- **Cross-Cutting (Phase 6)**: depends on Phase 2 (T003 adds `email_verified_at`) only — independent of Phases 3-5
- **Polish (Phase 7)**: depends on Phases 3-6 all being complete

### Parallel Opportunities

- T001, T002 in parallel (Setup)
- T004, T005, T007 in parallel after T003 (different files); T009, T010, T011 in parallel (different files, all depend on T005/T007)
- T014 parallel to T013/T015 (different file)
- T022 parallel to T021 (different file)
- T025 parallel to Phases 3-5 (different file, only depends on T003)
- T027, T028 in parallel; T029 last

---

## Implementation Strategy

### MVP First

Phase 1 → Phase 2 → Phase 3 (US1) → Phase 4 (US2) = minimum usable registration+confirmation loop. Phase 5 (US3, P2) and Phase 6 (FR-015) can ship after.

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. US1 (register) → US2 (confirm) → validate register→confirm loop manually (MVP)
3. US3 (resend) → validate cooldown/enumeration behavior
4. Cross-Cutting (FR-015) → validate `email_verified` on `001` admin endpoints
5. Polish → wire composition root, docs, full smoke test

---

## Notes

- No dedicated test tasks: spec.md/plan.md do not request tests for this feature; each phase checkpoint is a manual/independent verification step instead (per project's existing test posture — align with `001` if that feature has automated tests).
- FR-012 (never leak password hash/plain token) is enforced by construction across T013-T024 (schemas never include those fields) — no separate task.
- ADR-005's known ceiling (in-memory rate limiter, single-instance only) is inherited as-is by T015 — not re-litigated here.
