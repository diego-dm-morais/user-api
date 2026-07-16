# Implementation Plan: User CRUD API

**Branch**: `001-user-crud-api` | **Date**: 2026-07-15 | **Spec**: `specs/001-user-crud-api/spec.md`

**Input**: Feature specification from `specs/001-user-crud-api/spec.md`

## Summary

Serviço HTTP standalone para cadastro de usuários (create, read, update, delete, list, troca de senha) com Arquitetura Hexagonal: domínio puro (sem framework), casos de uso dependendo só de Ports, adapters inbound (FastAPI, protegido por API key) e outbound (PostgreSQL via SQLAlchemy async, hashing de senha via argon2id). Escopo do hexágono: todo o serviço, já que "cadastro de usuário" É o núcleo do projeto (nome do repo = `user-api`), não um módulo secundário — overhead de camadas se paga aqui, não é over-engineering.

## Technical Context

**Language/Version**: Python 3.13 (estável, suportado até 2029 em security fixes; 3.12 já em modo security-only desde abr/2025 — fonte: python.org/downloads e devguide.python.org/versions, verificado em 2026-07-15)

**Primary Dependencies**:
- `fastapi` (>=0.13, verificar `pip index versions fastapi` no momento do `uv add` — última estável confirmada em PyPI em 2026-07)
- `pydantic` v2 (>=2.13) — schemas de entrada/saída na borda HTTP, NÃO no domínio
- `sqlalchemy` 2.0.x async (>=2.0.51) + `asyncpg` — Adapter de persistência
- `alembic` — migrações
- `argon2-cffi` — hashing de senha (argon2id, recomendação OWASP atual para password hashing; preferido sobre bcrypt/passlib genérico)
- `pydantic-settings` — configuração via env vars (12-factor, sem secrets hardcoded)
- `uvicorn[standard]` — ASGI server

**Dev/Test Dependencies**: `pytest`, `pytest-asyncio`, `httpx` (AsyncClient para testes de contrato), `testcontainers[postgres]` (Postgres descartável em testes de integração — evita divergência de dialeto SQLite/Postgres em UUID/constraints), `ruff`, `mypy` (strict), `bandit`, `pip-audit`

**Storage**: PostgreSQL (produção e integração via testcontainers); UNIQUE constraint em `email` no banco garante corretude sob concorrência (FR-002/SC-004), não apenas checagem em aplicação.

**Testing**: pytest — unit (domínio + casos de uso com fakes de Port, sem I/O), integration (repository real contra Postgres efêmero), contract (formato de request/response e erros via httpx contra app FastAPI em memória).

**Target Platform**: Linux server / container (Docker), sem dependência de SO específico.

**Project Type**: web-service (API HTTP única, sem frontend nesta feature).

**Performance Goals**: p95 < 200ms em até 50 req/s (SC-001) — meta de referência, sem otimização prematura; medir com `pytest-benchmark` ou carga simples (`hey`/`locust`) antes de qualquer tuning.

**Constraints**: autenticação obrigatória do chamador via API key em todos os endpoints `/users*` (FR-014, ADR-004) — sem login/sessão de usuário final; sem cache (não há evidência de necessidade — YAGNI, adicionar Port de cache só se medição futura justificar).

**Scale/Scope**: dezenas de milhares de usuários, dezenas de req/s (assumido em spec.md) — dimensionamento simples (índice único em email, paginação limitada), sem sharding/particionamento nesta fase.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` está no template padrão, não ratificada para este projeto (nenhum princípio customizado definido ainda). Gate tratado como não-bloqueante: nenhuma violação a verificar até que o usuário rode `speckit-constitution` para fixar princípios do projeto. Recomendação registrada como risco remanescente no relatório final, não bloqueia esta feature.

## Project Structure

### Documentation (this feature)

```text
specs/001-user-crud-api/
├── plan.md              # This file
├── spec.md              # Feature specification
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

Fases Phase 0 (`research.md`) e Phase 1 (`data-model.md`, `contracts/`, `quickstart.md`) do template completo do Spec Kit foram dispensadas como arquivos separados: decisões de tecnologia já resolvidas acima (sem alternativas ambíguas restantes) e o modelo de dados é trivial (uma única entidade `User`) — documentado inline neste plano em vez de arquivos adicionais (ponytail: arquivo extra só quando há conteúdo real que justifique).

### Source Code (repository root)

```text
pyproject.toml
uv.lock
alembic.ini
.env.example

src/
└── user_api/
    ├── domain/
    │   ├── entities.py        # User (dataclass), value objects (Email)
    │   ├── exceptions.py      # DuplicateEmailError, UserNotFoundError, etc.
    │   └── ports.py           # Protocols: UserRepository, PasswordHasher, Clock
    ├── application/
    │   └── use_cases.py       # CreateUser, GetUser, ListUsers, UpdateUser, DeleteUser
    │                           # (funções/classes finas orquestrando ports; sem SQL/HTTP)
    ├── adapters/
    │   ├── inbound/
    │   │   └── http/
    │   │       ├── app.py          # FastAPI app factory (composition root)
    │   │       ├── routers.py      # /users endpoints (inclui PATCH /users/{id}/password)
    │   │       ├── schemas.py      # Pydantic request/response models
    │   │       ├── auth.py         # verify_api_key() — Depends() aplicado a todo router /users (FR-014, ADR-004)
    │   │       └── error_handlers.py  # mapeia exceções de domínio -> HTTP (FR-011)
    │   └── outbound/
    │       ├── persistence/
    │       │   ├── models.py       # SQLAlchemy ORM models
    │       │   ├── repository.py   # SqlAlchemyUserRepository(UserRepository)
    │       │   └── session.py      # engine/sessionmaker
    │       └── security/
    │           └── argon2_hasher.py  # Argon2PasswordHasher(PasswordHasher)
    └── config.py               # Settings (pydantic-settings): DATABASE_URL, API_KEY_HASHES (lista), lidas de env vars

tests/
├── unit/            # domínio + casos de uso, 100% fakes, sem I/O
├── integration/     # repository real contra Postgres via testcontainers
└── contract/        # httpx contra app, valida formato de erro (FR-010/FR-011) e contratos HTTP

migrations/          # Alembic versions
```

**Structure Decision**: Single project hexagonal (Option 1 adaptado). `domain/` sem nenhum import de `fastapi`/`sqlalchemy`/`pydantic` — verificável via `ruff`/import-linter em CI. `application/` (casos de uso) depende só de `domain.ports` (Protocols). `adapters/inbound/http` e `adapters/outbound/*` implementam os ports e são o único lugar onde framework/infra aparecem. Composition root (`app.py`) é quem instancia adapters concretos e injeta nos casos de uso via `Depends()` do FastAPI.

## ADR-001: Framework HTTP e ORM

**Contexto**: Precisa-se de um framework HTTP async e uma camada de acesso a dados para uma API CRUD greenfield em Python.

**Problema**: Qual stack HTTP + persistência minimiza esforço mantendo tipagem forte, validação e suporte async, sem contaminar o domínio.

**Alternativas consideradas**:
1. FastAPI + SQLAlchemy 2.x async + asyncpg
2. Flask + SQLAlchemy sync
3. Django + Django ORM (full-stack, admin embutido)
4. Litestar + SQLAlchemy async

**Vantagens (opção 1)**: tipagem nativa com Pydantic na borda, OpenAPI automático (requisito de "contratos claros" e documentação), async nativo casa com I/O-bound de uma API CRUD, ecossistema maduro, fácil isolar domínio (FastAPI só é importado em `adapters/inbound/http`).

**Desvantagens**: Pydantic não deve vazar para o domínio (mitigado: schemas Pydantic só na camada HTTP, domínio usa `dataclass`); Django traria muito mais do que o CRUD pedido (admin, ORM acoplado, templates) — rejeitado por overhead não solicitado (YAGNI). Litestar é mais novo, ecossistema/maturidade menor que FastAPI para este caso.

**Decisão**: FastAPI + SQLAlchemy 2.x async + asyncpg + Alembic.

**Trade-offs**: mais explícito que Django (sem admin/ORM "grátis"), mas alinhado a Hexagonal (o próprio Django ORM tende a acoplar modelo de domínio ao ORM, o que o sistema deve evitar).

**Impactos futuros**: troca de ORM ou de framework HTTP fica isolada nos adapters, sem tocar domínio/casos de uso — é exatamente o ponto da arquitetura hexagonal.

## ADR-002: Hashing de senha

**Contexto**: FR-003 exige que senha nunca seja armazenada em texto plano.

**Alternativas**: bcrypt (via `passlib`/`bcrypt`), scrypt, argon2id (via `argon2-cffi`).

**Vantagens (argon2id)**: vencedor da Password Hashing Competition, recomendação atual da OWASP Password Storage Cheat Sheet para novo desenvolvimento, resistente a ataques de hardware dedicado (GPU/ASIC) por ser memory-hard.

**Desvantagens**: uma dependência nativa (cffi) a mais para instalar/buildar; mitigado por já ter wheels pré-compilados para as plataformas alvo (Linux/container).

**Decisão**: `argon2-cffi`, parâmetros default da lib (revisar/calibrar custo conforme hardware de produção antes do primeiro deploy — não travar em número arbitrário agora).

**Trade-offs**: leve custo de build/deploy vs. postura de segurança recomendada atualmente.

**Impactos futuros**: `PasswordHasher` é um Port — trocar de argon2 para outro algoritmo no futuro não afeta domínio/casos de uso, só o adapter.

## ADR-003: Banco efêmero para testes de integração

**Contexto**: repository real precisa ser testado contra um banco que reproduza fielmente o dialeto de produção (UUID, UNIQUE constraint, timestamps).

**Alternativas**: SQLite in-memory (rápido, mas dialeto diferente — risco de falso-positivo em UNIQUE/UUID/JSONB), Postgres real compartilhado (risco de dados sujos entre execuções), Postgres via testcontainers (efêmero, isolado, paridade de dialeto).

**Decisão**: `testcontainers[postgres]` para os testes de `tests/integration/`. Testes unitários (`tests/unit/`) não tocam banco algum (usam fakes do Port).

**Trade-offs**: testes de integração ficam mais lentos que SQLite in-memory e exigem Docker disponível no ambiente de CI/local — aceitável porque só rodam em `tests/integration/`, não no ciclo rápido de `tests/unit/`.

**Impactos futuros**: nenhuma migração adicional necessária ao trocar de ambiente de teste, pois usa a mesma imagem Postgres da produção.

## ADR-004: Autenticação do chamador da API

**Contexto**: Round 2 do clarify (spec.md) confirmou que autenticação do cliente/serviço que chama a API é obrigatória já nesta entrega (FR-014), não fica fora de escopo. Não há requisito de login/sessão de usuário final — é autenticação de máquina-a-máquina.

**Problema**: Qual mecanismo autentica o chamador com menor complexidade possível, dado que não há IdP/OAuth server no escopo.

**Alternativas consideradas**:
1. API key estática (header `X-API-Key`, hash comparado via `hmac.compare_digest`)
2. JWT (chamador obtém token de um endpoint de login/token e o envia em `Authorization: Bearer`)
3. mTLS (certificado de cliente)

**Vantagens (opção 1 — API key)**: sem infraestrutura de emissão/assinatura/expiração/refresh de token; sem necessidade de um endpoint de "login" ou de gerenciar claims; validação é uma comparação de hash, stdlib (`hmac`, `hashlib`), sem dependência nova; adequado para autenticação de serviço-a-serviço (não há usuário final fazendo login nesta feature).

**Desvantagens**: sem expiração automática (mitigado por revogação manual: remover a key da config); sem granularidade de escopo/claims por chamador nesta v1 (YAGNI — não solicitado; se surgir necessidade de múltiplos clientes com permissões diferentes, revisar para JWT com claims ou tabela de keys com escopos).

**Por que não JWT**: JWT exigiria um endpoint de emissão de token (login) e gestão de assinatura/expiração/refresh — infraestrutura extra não solicitada e desproporcional para "autenticar o chamador da API", que aqui é um cliente de confiança fixo, não um usuário final com sessão. Adicionar quando houver necessidade real de tokens de curta duração ou múltiplos escopos de permissão.

**Por que não mTLS**: exige infraestrutura de PKI/certificados fora do escopo de uma API CRUD greenfield; overhead operacional não justificado agora.

**Decisão**: API key estática, enviada via header `X-API-Key`, validada por comparação em tempo constante (`hmac.compare_digest`) contra hash SHA-256 das keys configuradas em `Settings.API_KEY_HASHES` (env var, lista separada por vírgula). SHA-256 (não argon2) é adequado aqui porque a API key é um segredo de alta entropia gerado aleatoriamente, não uma senha de baixa entropia escolhida por humano — argon2 é overhead sem benefício de segurança nesse caso (ver OWASP Cheat Sheet: hashing lento é para proteger contra brute-force de segredos de baixa entropia).

**Escopo explicitamente fora desta feature (ponytail — evitar segundo CRUD não pedido)**: gestão de ciclo de vida da própria key (emissão, rotação, revogação via endpoint) não é modelada como entidade/tabela agora — keys são estáticas via env var. Adicionar API key management (tabela + endpoints) só quando houver múltiplos clientes precisando de rotação self-service sem redeploy.

**Trade-offs**: rotação de key requer redeploy/restart (aceitável no volume assumido); sem auditoria por-cliente de quem fez qual chamada nesta v1 (todas as keys válidas têm o mesmo nível de acesso).

**Impactos futuros**: `verify_api_key()` vive só no adapter HTTP (`adapters/inbound/http/auth.py`) — trocar para JWT/OAuth no futuro não toca domínio nem casos de uso, é um Depends() a substituir.

## ADR-005: Endpoint de troca de senha

**Contexto**: Round 2 do clarify confirmou que troca de senha é necessária já no MVP (FR-013), não fica fora de escopo.

**Problema**: Qual formato de endpoint expõe a troca de senha com menor superfície, dado que não há sessão de usuário final nem verificação de email (double opt-in já descartado).

**Alternativas consideradas**:
1. `PATCH /users/{id}/password` com body `{new_password}` — troca direta
2. `POST /users/{id}/password-reset` — fluxo de reset com token enviado por email/canal externo
3. Incluir `password` como campo opcional no `PATCH /users/{id}` já existente

**Vantagens (opção 1)**: espelha o padrão RESTful já usado nas demais operações (PATCH para atualização parcial), não exige infraestrutura de envio de email/token (que já foi descartada — "sem verificação de email" confirmado no round 2), rota dedicada deixa claro no OpenAPI que troca de senha é uma operação distinta (útil para auditoria/logging futuro, ex. logar toda troca de senha separadamente de troca de nome/email).

**Desvantagens**: sem exigência de "senha atual" para confirmar a troca — aceitável porque a autorização aqui é por API key do chamador (serviço confiável), não por sessão do usuário final (não há usuário final logado nesta feature); se no futuro houver login de usuário final, revisar para exigir senha atual ou reautenticação.

**Por que não opção 2 (reset com token)**: exigiria canal de envio (email/SMS) e gestão de token de reset com expiração — infraestrutura não solicitada e inconsistente com a decisão já tomada de não ter verificação de email nesta feature.

**Por que não opção 3 (campo no PATCH genérico)**: misturaria um dado sensível (senha) com dados não sensíveis (nome/email) no mesmo endpoint/schema, dificultando aplicar tratamento/log diferenciado a um campo de segurança; rota dedicada é mais clara e não é mais código.

**Decisão**: `PATCH /users/{id}/password`, body `{"new_password": str}`, valida mesma política mínima de FR-001, hasheia via `PasswordHasher` (mesmo Port do ADR-002), retorna 200 sem corpo de senha.

**Trade-offs**: sem confirmação de senha atual nesta v1 — ok dado o modelo de autorização por API key; revisar se/quando houver login de usuário final.

**Impactos futuros**: caso de uso `ChangePassword` reusa o mesmo `PasswordHasher` Port e `UserRepository.update()` — nenhuma peça nova de infraestrutura.

## ADR-006: `CreateUser` (admin) marca `email_verified_at` na criação

**Contexto**: `002-user-registration` introduziu `email_verified_at` e, via seu ADR-001, decidiu retroativamente popular `email_verified_at = created_at` para contas admin já existentes na migração (o fluxo admin nunca teve verificação de email; autorização é por API key, ver ADR-004 acima). Essa decisão de backfill deixava `CreateUser.execute` (caminho de criação, não a migração) inconsistente: novas contas admin continuavam nascendo com `email_verified_at = NULL`, teoricamente "pendentes" para sempre, já que nada no fluxo admin jamais confirma email.

**Decisão**: `CreateUser.execute` seta `email_verified_at=now` (mesmo `now` de `created_at`/`updated_at`) ao criar o usuário — mesmo raciocínio do backfill de `002/plan.md` ADR-001: fluxo admin é confiável (API key), verificação de email nunca foi a barreira de segurança aqui.

**Trade-offs**: nenhum novo — mesmos já aceitos em `002/plan.md` ADR-001 para o backfill.

**Impactos futuros**: se o fluxo admin (`POST /users`) algum dia aceitar cadastro por um chamador não confiável, revisar se `email_verified_at` deve voltar a `NULL` até confirmação real.

## Complexity Tracking

> Nenhuma violação de constitution a justificar (constitution ainda não ratificada para este projeto — ver Constitution Check acima).

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
