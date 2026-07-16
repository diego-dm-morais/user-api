# Tasks: User CRUD API

**Input**: Design documents from `specs/001-user-crud-api/` (spec.md, plan.md) — regenerado do zero em 2026-07-15 em cima do spec.md/plan.md pós round 2 do clarify (auth por API key + troca de senha incorporados).

**Prerequisites**: plan.md, spec.md

**Tests**: Incluídos — spec.md define critérios de aceite testáveis (SC-001..SC-005) e FR-003/FR-009/FR-014 são requisitos de segurança que exigem verificação automatizada.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 Inicializar projeto com `uv init` + `pyproject.toml` (Python 3.13), estrutura `src/user_api/` e `tests/{unit,integration,contract}/` conforme plan.md
- [X] T002 Adicionar dependências via `uv add fastapi sqlalchemy[asyncio] asyncpg alembic argon2-cffi pydantic-settings "uvicorn[standard]"` e dev deps via `uv add --dev pytest pytest-asyncio httpx "testcontainers[postgres]" ruff mypy bandit pip-audit` (auth por API key usa `hmac`/`hashlib` stdlib — sem dependência nova, ADR-004)
- [X] T003 [P] Configurar `ruff` (lint+format) e `mypy --strict` em `pyproject.toml`
- [X] T004 [P] Criar `.env.example` (inclui `DATABASE_URL`, `API_KEY_HASHES`) e `.gitignore` (excluir `.env`, `__pycache__`, `.venv`)

**Checkpoint**: Projeto instala e roda `pytest --collect-only` sem erros.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: base que todas as user stories dependem, incluindo autenticação por API key (FR-014, ADR-004) — obrigatória em todo `/users*` desde o round 2 do clarify.

**⚠️ CRITICAL**: nenhuma user story começa antes desta fase.

- [X] T005 Domínio: `src/user_api/domain/entities.py` — dataclass `User` (id: UUID, name, email, password_hash, created_at, updated_at, deleted_at)
- [X] T006 [P] Domínio: `src/user_api/domain/exceptions.py` — `DuplicateEmailError`, `UserNotFoundError`
- [X] T007 [P] Domínio: `src/user_api/domain/ports.py` — Protocols `UserRepository`, `PasswordHasher`, `Clock`
- [X] T008 Config: `src/user_api/config.py` — `Settings(BaseSettings)` lendo `DATABASE_URL` e `API_KEY_HASHES` (lista de hashes SHA-256 separados por vírgula) de env vars (sem secrets hardcoded)
- [X] T009 Persistência: `src/user_api/adapters/outbound/persistence/models.py` — SQLAlchemy ORM `UserModel` com UNIQUE partial index em `email` via `Index(..., postgresql_where=text("deleted_at IS NULL"))` (Postgres é o banco fixado no plan.md, sem fallback de dialeto)
- [X] T010 Persistência: `src/user_api/adapters/outbound/persistence/session.py` — engine async + sessionmaker
- [X] T011 Migrações: inicializar Alembic (`migrations/`) e gerar migração inicial da tabela `users`
- [X] T012 [P] Segurança: `src/user_api/adapters/outbound/security/argon2_hasher.py` — `Argon2PasswordHasher` implementando `PasswordHasher` (ADR-002)
- [X] T013 [P] Segurança/HTTP: `src/user_api/adapters/inbound/http/auth.py` — `verify_api_key(x_api_key: str = Header(...))`, hasheia com SHA-256 e compara via `hmac.compare_digest` contra `Settings.API_KEY_HASHES`; 401 se ausente/inválida (FR-014, ADR-004)
- [X] T014 HTTP: `src/user_api/adapters/inbound/http/error_handlers.py` — mapeia `DuplicateEmailError`→409, `UserNotFoundError`→404, `RequestValidationError`→422, formato de erro consistente (FR-011)
- [X] T015 HTTP: `src/user_api/adapters/inbound/http/app.py` — FastAPI app factory (composition root), registra error handlers, aplica `Depends(verify_api_key)` a todo o router `/users*` (depende de T013), wiring de dependências

### Tests for Foundational (Auth)

- [X] T016 [P] Contract test: qualquer endpoint de `/users*` sem `X-API-Key` ou com key inválida → 401, nenhum dado de usuário no corpo (FR-014, SC-005); inclui caso key malformada (string arbitrária, não corresponde a nenhum hash) vs key ausente/inexistente — assert que o corpo da resposta é byte-a-byte idêntico nos dois cenários (mensagem genérica, sem distinguir motivo) em `tests/contract/test_auth.py`

**Checkpoint**: fundação pronta (persistência + auth) — user stories podem ser implementadas.

---

## Phase 3: User Story 1 - Registrar novo usuário (Priority: P1) 🎯 MVP

**Goal**: POST `/users` cria usuário com senha hasheada, rejeita email duplicado e payload inválido. Requer API key válida (herdado da Foundational).

**Independent Test**: POST `/users` válido (com API key) → 201; repetir mesmo email → 409; payload inválido → 422; sem API key → 401.

### Tests for User Story 1

- [X] T017 [P] [US1] Contract test POST `/users` (201, 409, 422); no 201 assert explícito que a resposta não contém `password_hash` nem qualquer campo de senha (SC-003) em `tests/contract/test_create_user.py`
- [X] T018 [P] [US1] Integration test `SqlAlchemyUserRepository.add` + UNIQUE constraint em `tests/integration/test_user_repository.py`
- [X] T019 [P] [US1] Unit test `CreateUser` use case (fake repository + fake hasher) em `tests/unit/test_create_user.py`
- [X] T020 [US1] Teste de concorrência: 2 criações simultâneas mesmo email → 1 sucesso + 1 conflito (SC-004) em `tests/integration/test_create_user_concurrency.py`

### Implementation for User Story 1

- [X] T021 [P] [US1] `src/user_api/adapters/outbound/persistence/repository.py` — `SqlAlchemyUserRepository.add()` (depende de T009, T010)
- [X] T022 [US1] `src/user_api/application/use_cases.py` — `CreateUser` (valida via ports, hasheia senha, chama repository; depende de T005-T007, T012)
- [X] T023 [P] [US1] `src/user_api/adapters/inbound/http/schemas.py` — `UserCreateRequest`/`UserResponse` (Pydantic, nunca expõe password_hash)
- [X] T024 [US1] `src/user_api/adapters/inbound/http/routers.py` — `POST /users` (depende de T022, T023, T013)

**Checkpoint**: User Story 1 funcional e testável isoladamente (MVP mínimo do cadastro).

---

## Phase 4: User Story 2 - Consultar usuário(s) (Priority: P1)

**Goal**: GET `/users/{id}` e GET `/users` (paginado) retornam apenas usuários ativos.

**Independent Test**: GET por id existente → 200; id inexistente/soft-deleted → 404; listagem paginada com metadados; sem API key → 401.

### Tests for User Story 2

- [X] T025 [P] [US2] Contract test GET `/users/{id}` (200, 404); no 200 assert explícito que a resposta não contém `password_hash` nem qualquer campo de senha (SC-003) em `tests/contract/test_get_user.py`
- [X] T026 [P] [US2] Contract test GET `/users` paginado; para cada item da lista, assert explícito que não contém `password_hash` nem qualquer campo de senha (SC-003) em `tests/contract/test_list_users.py`
- [X] T027 [P] [US2] Unit test `GetUser`/`ListUsers` use cases em `tests/unit/test_query_users.py`
- [X] T027a [P] [US2] Contract test GET `/users` com `page`/`page_size` fora dos limites — casos: negativo, zero, string não-numérica, valor gigante (> max) — todos devem retornar 422 (nunca 500) em `tests/contract/test_list_users_pagination.py`

### Implementation for User Story 2

- [X] T028 [P] [US2] `SqlAlchemyUserRepository.get_by_id()` / `list_paginated()` (filtra `deleted_at IS NULL`) em `repository.py`
- [X] T029 [US2] `src/user_api/application/use_cases.py` — `GetUser`, `ListUsers` (depende de T028)
- [X] T030 [P] [US2] `schemas.py` — `UserListResponse` com metadados (total, page, page_size)
- [X] T031 [US2] `routers.py` — `GET /users/{id}`, `GET /users?page=&page_size=` com limites de paginação (default 20, max 100, 422 se fora do range)

**Checkpoint**: US1+US2 funcionais — cadastro criável e consultável.

---

## Phase 5: User Story 3 - Atualizar cadastro (Priority: P2)

**Goal**: PATCH `/users/{id}` atualiza nome/email parcialmente, rejeita email duplicado. PATCH `/users/{id}/password` troca a senha (FR-013, ADR-005).

**Independent Test**: PATCH nome → 200 só nome muda; PATCH email já usado → 409; id inexistente → 404; PATCH senha válida → 200 sem devolver hash; PATCH senha fraca → 422.

### Tests for User Story 3

- [X] T032 [P] [US3] Contract test PATCH `/users/{id}` (200, 404, 409); no 200 assert explícito que a resposta não contém `password_hash` nem qualquer campo de senha (SC-003) em `tests/contract/test_update_user.py`
- [X] T033 [P] [US3] Unit test `UpdateUser` use case em `tests/unit/test_update_user.py`
- [X] T034 [P] [US3] Contract test PATCH `/users/{id}/password` (200, 404, 422; resposta nunca contém senha/hash — FR-013, SC-003) em `tests/contract/test_change_password.py`
- [X] T035 [P] [US3] Unit test `ChangePassword` use case (fake repository + fake hasher) em `tests/unit/test_change_password.py`

### Implementation for User Story 3

- [X] T036 [US3] `SqlAlchemyUserRepository.update()` em `repository.py` — persiste nome/email e também `password_hash`/`updated_at` (reusado por `UpdateUser` e `ChangePassword`, sem método novo no repository)
- [X] T037 [US3] `application/use_cases.py` — `UpdateUser` (checa conflito de email antes de persistir; depende de T036)
- [X] T038 [US3] `application/use_cases.py` — `ChangePassword` (valida política mínima de senha, hasheia via `PasswordHasher`, persiste via T036; depende de T012, T036)
- [X] T039 [P] [US3] `schemas.py` — `UserUpdateRequest` (todos campos opcionais) e `ChangePasswordRequest` (`new_password: str`)
- [X] T040 [US3] `routers.py` — `PATCH /users/{id}` (depende de T037) e `PATCH /users/{id}/password` (depende de T038)

**Checkpoint**: US1+US2+US3 funcionais, incluindo troca de senha.

---

## Phase 6: User Story 4 - Remover usuário (Priority: P3)

**Goal**: DELETE `/users/{id}` faz soft-delete; leitura subsequente retorna 404.

**Independent Test**: DELETE existente → 204; GET depois → 404; DELETE de novo → 404.

### Tests for User Story 4

- [X] T041 [P] [US4] Contract test DELETE `/users/{id}` (204, 404) em `tests/contract/test_delete_user.py`
- [X] T042 [P] [US4] Unit test `DeleteUser` use case em `tests/unit/test_delete_user.py`

### Implementation for User Story 4

- [X] T043 [US4] `SqlAlchemyUserRepository.soft_delete()` (seta `deleted_at`) em `repository.py`
- [X] T044 [US4] `application/use_cases.py` — `DeleteUser` (depende de T043)
- [X] T045 [US4] `routers.py` — `DELETE /users/{id}`

**Checkpoint**: Todas as 5 operações de CRUD + troca de senha funcionais, independentemente testáveis, todas atrás de API key.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T045a [P] Contract test cross-endpoint: coleta um caso de erro de cada endpoint (401 sem API key em qualquer rota, 404 GET `/users/{id}` inexistente, 409 POST `/users` email duplicado, 422 POST `/users` payload inválido) e assert que todos seguem o mesmo schema de erro (mesmas chaves/tipos, produzido por `error_handlers.py` — FR-011, SC-002) em `tests/contract/test_error_format_consistency.py` (depende de US1-US4 completas para gerar todos os cenários; por isso vive em Polish, não em Foundational)
- [X] T046 [P] Logging estruturado (JSON) via stdlib `logging` com request id, aplicado nos adapters (nunca no domínio) — logar troca de senha (T038) como evento de segurança distinto, sem logar a senha em si
- [X] T047 [P] Healthcheck `GET /health` (liveness, sem exigir API key) e verificação de conexão DB (readiness)
- [X] T048 [P] Rodar `bandit -r src/` e `pip-audit` — corrigir achados antes de considerar pronto
- [X] T049 CI: pipeline com `ruff check`, `mypy --strict`, `pytest tests/unit tests/contract`, `pytest tests/integration` (requer Docker), `bandit`, `pip-audit`
- [X] T050 Validar SC-001 (p95 < 200ms @ 50 req/s) com carga simples — só otimizar se medição reprovar
- [X] T051 Documentar em `.env.example`/README curto como gerar e configurar `API_KEY_HASHES` (`python -c "import secrets,hashlib; k=secrets.token_urlsafe(32); print(k, hashlib.sha256(k.encode()).hexdigest())"`)

---

## Dependencies & Execution Order

### Phase Dependencies

- Setup (Phase 1) → Foundational (Phase 2, inclui persistência + auth) → bloqueia todas as user stories
- User Stories (Phase 3-6): todas dependem de Foundational completa
- Polish (Phase 7): depende de todas as user stories desejadas estarem completas

### User Story Dependencies

- US1 (P1) e US2 (P1) podem rodar em paralelo após Foundational — sem dependência mútua
- US3 (P2): depende conceitualmente de US1/US2 existirem para ter algo a atualizar, mas não é bloqueio técnico (pode ser implementada com dados de teste próprios)
- US4 (P3): idem, sem bloqueio técnico de US1/US2/US3
- Dentro de US3: `ChangePassword` (T035, T038, T040-parte2) não depende de `UpdateUser` (T033, T037, T040-parte1) — arquivos/rotas distintos, paralelizável por pessoas diferentes apesar de estarem na mesma fase

### Parallel Opportunities

- Todas as tasks `[P]` de uma mesma fase: arquivos diferentes, sem dependência mútua, paralelizáveis
- Uma vez Foundational completa, US1 e US2 podem ser times/sessões diferentes em paralelo

---

## Implementation Strategy

### MVP First

1. Phase 1 (Setup) + Phase 2 (Foundational, com auth) + Phase 3 (US1: criar usuário, já atrás de API key)
2. **STOP and VALIDATE**: rodar T016-T020 e confirmar 201/409/422/401 e SC-004
3. Deploy/demo se pronto

### Incremental Delivery

Foundation → US1 (MVP) → US2 (consulta) → US3 (update + troca de senha) → US4 (soft-delete) → Polish. Cada fase adiciona valor sem quebrar a anterior.

## Notes

- Total: 54 tasks (T001-T051 + T016 expandida + T027a, T045a)
- FR-013 (troca de senha) coberto por T034, T035, T038, T039, T040
- FR-014 (API key obrigatória) coberto por T013, T015, T016
- SC-002 (formato de erro consistente entre endpoints) coberto por T014 (implementação) e T045a (teste cross-endpoint)
- SC-003 (nunca vazar password hash) coberto por T017, T025, T026, T032, T034 (assert explícito de ausência do campo em cada resposta de create/get/list/update/change-password)
- SC-005 (401 sem API key válida, mensagem genérica idêntica para key ausente e malformada) coberto por T016
- Edge case "page/page_size fora dos limites → sempre 422" coberto por T027a
- T009 usa sintaxe de índice parcial do Postgres diretamente (`postgresql_where`), sem condicional de dialeto — banco fixado no plan.md
- Nenhuma task cria CRUD de gestão de API key (fora de escopo, ver ADR-004/spec.md Assumptions)
