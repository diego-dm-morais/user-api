# Implementation Plan: Self-Service User Registration

**Branch**: `002-user-registration` | **Date**: 2026-07-15 | **Spec**: `specs/002-user-registration/spec.md`

**Input**: Feature specification from `specs/002-user-registration/spec.md`

## Summary

Fluxo público de auto-cadastro (`POST /auth/register`, `GET /auth/confirm`, `POST /auth/register/resend`), sem API key, com conta em estado `pending` até confirmação de email por token. Reusa a entidade `User`, o Port `PasswordHasher` (argon2id) e o Port `Clock` já existentes em `001-user-crud-api`; adiciona um agregado leve `EmailVerificationToken`, dois novos Ports (`TokenGenerator`, `EmailSender`) e três novos casos de uso (`RegisterUser`, `ConfirmEmail`, `ResendVerificationEmail`). Nenhuma mudança em `001` além de: (1) migração aditiva em `users` (`email_verified_at`), (2) `UserResponse` ganhar `email_verified: bool`.

## Technical Context

Mesma stack de `001` (Python 3.13, FastAPI, SQLAlchemy 2.x async, argon2-cffi, Alembic) — sem dependência nova para o core do fluxo. Envio de email na v1 é um adapter log/console (ver ADR-003, decisão revista em `speckit-clarify`); rate limiting por IP em `POST /auth/register` é um novo componente in-app (ver ADR-005).

## Constitution Check

Mesmo estado de `001`: constitution não ratificada, gate não-bloqueante (risco remanescente já registrado em `001`, não duplicado aqui).

## Bounded Context / Encaixe na Arquitetura Hexagonal

Não é um novo bounded context — é o mesmo bounded context de identidade/cadastro de `001`, com um segundo caso de uso de escrita (criação) e um sub-fluxo de confirmação, expostos por um adapter inbound HTTP diferente (`/auth/*` público em vez de `/users*` autenticado por API key). Reusa `domain/entities.py::User` em vez de criar um agregado `PendingRegistration` paralelo — evitaria duplicar a lógica de unicidade de email e a constraint de banco já existente em `001` (violaria DRY/YAGNI sem benefício: não há regra de negócio que trate "usuário pendente" como um conceito distinto de "usuário", apenas um estado a mais).

```text
src/user_api/
├── domain/
│   ├── entities.py           # User ganha email_verified_at; + EmailVerificationToken (novo dataclass)
│   ├── exceptions.py         # + InvalidOrExpiredTokenError, ResendCooldownError
│   └── ports.py               # + TokenGenerator, EmailSender
├── application/
│   └── registration_use_cases.py   # RegisterUser, ConfirmEmail, ResendVerificationEmail (novo módulo,
│                                     # não mistura com use_cases.py de 001 — fluxo público vs. admin)
├── adapters/
│   ├── inbound/http/
│   │   ├── auth_router.py     # /auth/register, /auth/confirm, /auth/register/resend — SEM verify_api_key
│   │   ├── schemas.py         # + RegisterRequest, ResendRequest (reusa MIN_PASSWORD_LENGTH)
│   │   └── ip_rate_limiter.py # dependency FastAPI: contador in-memory por IP + janela deslizante (ADR-005)
│   └── outbound/
│       ├── persistence/
│       │   ├── models.py      # UserModel += email_verified_at; + EmailVerificationTokenModel
│       │   └── token_repository.py   # EmailVerificationTokenRepository(TokenRepositoryPort)
│       ├── security/
│       │   └── token_generator.py    # SecretsTokenGenerator (stdlib secrets.token_urlsafe)
│       └── notifications/
│           └── console_email_sender.py  # ConsoleEmailSender(EmailSender) — loga token/link, sem envio real (v1)
└── config.py                  # + AUTH_REGISTER_RATE_LIMIT (env var, ex. "10/60s"); sem SMTP config na v1

migrations/versions/
└── xxxxxxxxxxxx_add_email_verification.py   # ALTER users ADD email_verified_at; CREATE email_verification_tokens
```

**Por que módulo de use cases separado (`registration_use_cases.py`)**: `001` já teve 5 casos de uso em `use_cases.py` (~110 linhas); os 3 novos são de um fluxo público distinto (sem API key), com dependências parcialmente diferentes (`TokenGenerator`, `EmailSender`) — separar mantém cada arquivo <500 linhas (regra do projeto) e a fronteira admin-vs-público legível sem precisar ler docstrings.

## Novos Ports

```python
# domain/ports.py (adição)

class TokenGenerator(Protocol):
    def generate(self) -> str:
        """Retorna um token de alta entropia (URL-safe) em texto plano."""
        ...

class EmailSender(Protocol):
    async def send_verification_email(self, to: str, token: str) -> None:
        """Envia o link/token de confirmação. Falha deve levantar exceção
        (adapter decide retry/log); use case NÃO reverte a criação da conta
        por falha de envio (ver Assumptions em spec.md)."""
        ...
```

`TokenGenerator` existe como Port (e não `secrets.token_urlsafe()` chamado direto no use case) pelo mesmo motivo de `Clock` já existir em `001`: geração não-determinística precisa de fake determinístico em teste de unidade do use case, sem tocar `secrets` real.

`EmailSender` é async (I/O de rede) — consistente com o resto do projeto ser async end-to-end (`UserRepository`, FastAPI).

## Novo Agregado leve: EmailVerificationToken

```python
# domain/entities.py (adição)

@dataclass
class EmailVerificationToken:
    id: UUID
    user_id: UUID
    token_hash: str          # sha256(token) — mesmo padrão de comparação de API key em 001 (hmac.compare_digest)
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None = None

    @property
    def is_valid(self, now: datetime) -> bool:
        return self.used_at is None and now < self.expires_at
```

Token em claro nunca é persistido (mesmo raciocínio de ADR-004 de `001`: alta entropia, hash SHA-256 simples basta, não é senha de baixa entropia — argon2 seria overhead sem benefício).

## Casos de Uso

### RegisterUser

```python
@dataclass
class RegisterUser:
    repository: UserRepository
    token_repository: EmailVerificationTokenRepository
    hasher: PasswordHasher
    token_generator: TokenGenerator
    email_sender: EmailSender
    clock: Clock

    async def execute(self, name: str, email: str, password: str) -> None:
        _check_password_policy(password)
        existing = await self.repository.get_by_email(email)  # ativos E pendentes (ver nota)
        if existing is not None:
            if existing.email_verified_at is None:
                await self._reissue_token_if_not_in_cooldown(existing)  # mesma checagem de 60s de ResendVerificationEmail (FR-009) — evita bypass do cooldown trocando de endpoint
            return  # FR-010: sempre 202, sem sinalizar diferença (sucesso silencioso; sem exceção 429 aqui, diferente de /resend)

        now = self.clock.now()
        user = User(id=uuid4(), name=name, email=email,
                     password_hash=self.hasher.hash(password),
                     created_at=now, updated_at=now, email_verified_at=None)
        await self.repository.add(user)
        await self._issue_token(user)
```

Nota: `UserRepository.get_by_email` em `001` retorna só ativos (`deleted_at IS NULL`); FR-013 pede reuso da constraint de unicidade — a query de registro precisa também enxergar contas *pendentes não confirmadas* para aplicar FR-010/edge case "email pendente reemite token". Ajuste mínimo: adicionar `get_by_email_including_pending()` ao Port (ou parametrizar) — detalhado na seção Impacto em `001`.

### ConfirmEmail

```python
@dataclass
class ConfirmEmail:
    token_repository: EmailVerificationTokenRepository
    repository: UserRepository
    clock: Clock

    async def execute(self, token: str) -> None:
        record = await self.token_repository.get_by_token(token)  # compara hash internamente
        now = self.clock.now()
        if record is None or not record.is_valid(now):
            raise InvalidOrExpiredTokenError()
        await self.token_repository.mark_used(record.id, now)
        await self.repository.mark_email_verified(record.user_id, now)
```

### ResendVerificationEmail

```python
@dataclass
class ResendVerificationEmail:
    repository: UserRepository
    token_repository: EmailVerificationTokenRepository
    token_generator: TokenGenerator
    email_sender: EmailSender
    clock: Clock

    async def execute(self, email: str) -> None:
        user = await self.repository.get_by_email_including_pending(email)
        if user is None or user.email_verified_at is not None:
            return  # FR-010: sucesso silencioso, sem revelar estado
        last = await self.token_repository.get_latest_for_user(user.id)
        now = self.clock.now()
        if last is not None and (now - last.created_at).total_seconds() < 60:
            raise ResendCooldownError()
        await self._issue_token(user)
```

`ResendCooldownError` é o único caso em que a resposta HTTP **não** é genérica (429 em vez de 202) — exceção documentada e resolvida em `spec.md` FR-010/SC-001 (`speckit-clarify`/`speckit-analyze`, 2026-07-15): cooldown é rate limiting de abuso, não enumeração deliberada; risco residual (429 só é alcançável quando existe conta pendente) é aceito conscientemente, não é bug a corrigir.

## Fluxo passo a passo

**Registro:**
1. `POST /auth/register` (sem auth) → `auth_router.py` valida payload via Pydantic (`RegisterRequest`, 422 se inválido).
2. Router injeta `RegisterUser` (composition root) e chama `.execute()`.
3. Use case verifica duplicidade (ativo ou pendente) via `UserRepository`.
4. Se novo: hasheia senha (`PasswordHasher`), persiste `User` (`deleted_at=None`, `email_verified_at=None`).
5. Gera token (`TokenGenerator`), hasheia (SHA-256) e persiste `EmailVerificationToken` (`TokenRepository`).
6. Dispara `EmailSender.send_verification_email(email, token_em_claro)` — token em claro só existe em memória e no email, nunca no banco.
7. Router responde 202 com corpo genérico, independente do que aconteceu no passo 3-6 (FR-010).

**Confirmação:**
1. `GET /auth/confirm?token=X` (sem auth) → router chama `ConfirmEmail.execute(token)`.
2. Use case busca token por hash, valida `is_valid` (não usado, não expirado).
3. Marca token como usado + marca `User.email_verified_at` no repositório, na mesma unidade lógica (idealmente uma transação — ver ADR-004).
4. Router responde 200 (sucesso) ou 410/400 conforme exceção mapeada em `error_handlers.py`.

**Reenvio:** análogo ao registro, sem criar novo `User`, sujeito a cooldown.

## Rate limiting por IP em `POST /auth/register`

FR-014/SC-006: dependency FastAPI (`ip_rate_limiter.py`) injetada só na rota `POST /auth/register`, antes do use case — contador in-memory (`dict[str, deque[datetime]]`) por IP com janela deslizante (ex.: 10 req/60s, configurável via `AUTH_REGISTER_RATE_LIMIT`). Acima do limite: 429 direto no adapter HTTP, sem chegar no domínio (não é regra de negócio, é proteção de infraestrutura — por isso não vira Port).

**Ceiling explícito (ponytail: contador in-memory, upgrade se escalar)**: estado vive na memória do processo — correto para instância única; com múltiplas réplicas atrás de um load balancer, cada instância conta seu próprio IP e o limite efetivo multiplica pelo número de réplicas (contadores não são compartilhados). Não é um bug a corrigir agora (YAGNI: projeto roda single-instance, ver Assumptions do spec.md); é o limite conhecido da abordagem. Upgrade path quando escalar horizontalmente: mover o contador para um store compartilhado (Redis, `INCR` + `EXPIRE`), trocando apenas a implementação da dependency, sem tocar rota ou use case. Ver ADR-005.

## Erros e mapeamento HTTP

| Exceção de domínio | HTTP | Observação |
|---|---|---|
| `WeakPasswordError` | 422 | Igual a `001`. |
| `InvalidOrExpiredTokenError` | 400 | Mensagem genérica — não distingue "não existe" vs "expirado" vs "já usado" (FR-011), decisão final confirmada em `speckit-analyze` (2026-07-15): sempre 400, nunca 410, nas quatro condições (ver spec.md US2 Acceptance Scenario 2). |
| `ResendCooldownError` | 429 | Único caso não-genérico, é rate limiting, não enumeração. |
| (duplicidade de email) | — | Nunca vira erro HTTP aqui (FR-010) — resolvido internamente no use case. |
| (rate limit de IP excedido) | 429 | FR-014/SC-006 — gerado no adapter HTTP (`ip_rate_limiter.py`) antes de chamar o use case; não é exceção de domínio. |

## Impacto em `001-user-crud-api` (mudanças aditivas, não-breaking)

1. **Migração aditiva**: `ALTER TABLE users ADD COLUMN email_verified_at TIMESTAMPTZ NULL` + `CREATE TABLE email_verification_tokens`. Não quebra dados existentes (usuários criados via `001`/admin ficam com `email_verified_at = NULL` por padrão, ou — decisão a confirmar — populados com `created_at` na migração, já que cadastro admin nunca teve verificação; ver ADR-001 abaixo).
2. **`UserRepository` (Port)**: dois métodos novos — `get_by_email_including_pending(email) -> User | None` e `mark_email_verified(user_id, when) -> None`. Implementados no mesmo `SqlAlchemyUserRepository` de `001` (adapter existente, sem novo repositório para `User`).
3. **`UserResponse` (schema HTTP de `001`)**: `+ email_verified: bool` (derivado de `email_verified_at is not None`) — aditivo, não quebra consumidores existentes que ignoram campos novos. Atende FR-015/SC-007 (`GET /users` e `GET /users/{id}`). Não exige novo método de repositório: `email_verified_at` já é persistido pela migração do item 1 e já vem no `UserModel`/`User` retornado por `SqlAlchemyUserRepository.get_by_id`/`list_all` (adapter existente de `001`); a mudança é só no schema de saída (`UserResponse`), mapeando o atributo já disponível.

## ADR-001: Usuários administrativos (criados via `001`) são retroativamente "verificados"?

**Contexto**: migração adiciona `email_verified_at`; usuários já existentes (criados via `POST /users` administrativo) não passaram por nenhum fluxo de confirmação.

**Alternativas**: (a) `NULL` para todos os existentes (tratados como pendentes retroativamente); (b) `created_at` copiado para `email_verified_at` na migração (tratados como já verificados, já que o fluxo admin nunca exigiu isso e é operado por um chamador de confiança).

**Decisão**: (b) — popular `email_verified_at = created_at` para todas as linhas existentes na migração. Contas criadas pelo fluxo admin continuam operando normalmente sem ficarem subitamente "pendentes" por uma regra que não existia quando foram criadas.

**Trade-offs**: nenhuma verificação real ocorreu para essas contas — aceitável porque o modelo de confiança de `001` já é "quem tem API key pode criar/editar qualquer usuário" (ADR-004 de `001`), então a verificação de email nunca foi a barreira de segurança ali.

**Impactos futuros**: se `email_verified` passar a gatilhar alguma feature de login, revisar se contas admin-criadas devem re-confirmar.

## ADR-002: Resposta genérica em vez de 409 para email já cadastrado

**Contexto**: `001` retorna 409 explícito em duplicidade (FR-002 de `001`) porque o chamador é autenticado/confiável (API key). Aqui o chamador é anônimo.

**Alternativas**: 1) espelhar `001` e retornar 409; 2) resposta 202 genérica sempre (FR-010 desta spec).

**Vantagens (opção 2)**: previne user enumeration (OWASP ASVS 2.1: não revelar se uma conta existe via mensagem de erro em fluxo de registro público) — um chamador anônimo não deve conseguir testar em massa quais emails já têm conta.

**Desvantagens**: UX pior (usuário legítimo que já tem conta e tenta recadastrar não recebe feedback claro; precisa depender do "esqueci minha senha" — que está fora de escopo aqui, ver Assumptions). Mitigado pela mensagem do 202 sugerir "se esse email já tem conta, você não receberá um novo email de boas-vindas" (texto, não implementação).

**Decisão**: opção 2, resposta genérica sempre — segurança (ordem de prioridade #1 deste papel) prevalece sobre conveniência de UX aqui, e o dado protegido (existência de conta associada a um email) é PII sensível a enumeração.

**Trade-offs**: suporte ao usuário pode precisar de um canal alternativo (ex. "não recebi o email") fora do escopo desta feature.

**Impactos futuros**: se o produto priorizar UX sobre anti-enumeração no futuro, reverter é uma mudança pontual no `error_handlers.py`/use case, sem tocar domínio.

## ADR-003: Adapter de envio de email

**Contexto**: precisa-se enviar o token de confirmação por email; não há provedor transacional definido no projeto ainda. Recomendação original deste plano era `smtplib` (stdlib) contra SMTP configurado via env var; `speckit-clarify` (2026-07-15) decidiu diferente — ver Decisão.

**Alternativas**: 1) `smtplib` (stdlib) contra um servidor SMTP configurado via env var; 2) SDK de provedor (SES/SendGrid/Postmark) — nova dependência; 3) fila de mensagens (Celery/RQ) para envio assíncrono desacoplado do request; 4) adapter log/console — loga o token/link de confirmação, sem envio real.

**Vantagens (opção 4, decidida)**: zero dependência nova e zero infraestrutura externa (nem servidor SMTP) para v1 — não há provedor/servidor de email contratado ainda no projeto, então até `smtplib` exigiria uma peça de infra que não existe; permite testar o fluxo completo de confirmação em dev/CI lendo o log; `EmailSender` é um Port — trocar para SMTP/SES/SendGrid depois é só um novo adapter, sem tocar use case nem domínio.

**Desvantagens**: v1 não envia email real — inutilizável para usuários finais reais até um adapter de produção existir; isso é uma limitação de escopo aceita explicitamente (ver Assumptions do spec.md), não um débito técnico escondido.

**Decisão**: adapter `ConsoleEmailSender` (log/console) para v1, implementando o Port `EmailSender` sem alteração de assinatura. Nenhum adapter de produção (SMTP ou SDK de provedor) é implementado nesta versão — fica para quando o provedor/infra de envio estiver definido. **Bloqueio de deploy**: este adapter não deve ir para produção pública real enquanto o adapter de produção não existir; é adequado apenas para dev/staging/demo.

**Trade-offs**: sem dashboard de entregabilidade; sem envio real (limitação aceita, não parcial).

**Impactos futuros**: troca de adapter isolada em `adapters/outbound/notifications/` (`console_email_sender.py` → `smtp_email_sender.py` ou SDK de provedor), sem tocar `application/registration_use_cases.py` nem `domain/`, pois ambos dependem apenas do Port.

## ADR-004: Consistência entre marcar token usado e marcar usuário verificado

**Contexto**: `ConfirmEmail.execute()` faz duas escritas (token + user). Se a segunda falhar após a primeira, token fica "queimado" sem a conta ter sido ativada.

**Alternativas**: 1) duas chamadas de repositório independentes (como no pseudocódigo acima), aceitando a janela de inconsistência; 2) uma transação de banco única cobrindo as duas escritas, exposta via um único método de repositório (`UserRepository.confirm_email(user_id, token_id, when)` ou repositório compartilhado).

**Decisão**: opção 2 na implementação real — método único no adapter de persistência que abre uma transação SQLAlchemy cobrindo ambas as tabelas (`users` e `email_verification_tokens`), exposto ao use case como uma única chamada de Port (ex.: `EmailVerificationTokenRepository.consume_and_verify(token_hash, now) -> UUID | None`, retornando o `user_id` ou `None` se inválido). Evita a janela de inconsistência sem introduzir um Port de "Unit of Work" genérico (YAGNI — `001` também não tem um, cada operação já é atômica por repositório).

**Trade-offs**: acopla ligeiramente as duas tabelas em um método de repositório (mistura responsabilidade de "token" e "user") — aceitável porque é a única operação com essa necessidade transacional; não generalizar para um padrão maior sem outro caso de uso que precise.

**Impactos futuros**: se surgir uma terceira operação cross-tabela, reconsiderar Unit of Work explícito.

## ADR-005: Rate limiting por IP em `POST /auth/register`

**Contexto**: FR-014/SC-006 exigem rate limit por IP nesse endpoint, implementado na aplicação (não delegado a gateway externo) — decisão de `speckit-clarify` (2026-07-15); recomendação original deste plano era delegar a um gateway/proxy (fora do escopo de código da aplicação).

**Alternativas**: 1) delegar a gateway/API proxy externo (nginx, API Gateway) — zero código na aplicação, mas fora do controle do repositório e não testável em CI; 2) contador in-memory por IP com janela deslizante, embutido como dependency/middleware FastAPI; 3) store compartilhado (Redis) desde já.

**Vantagens (opção 2, decidida)**: sem dependência nova, sem infraestrutura extra (nenhum Redis contratado no projeto ainda), testável em CI como qualquer outro componente da aplicação, atende single-instance (contexto atual do projeto — ver Assumptions do spec.md).

**Desvantagens**: não funciona corretamente com múltiplas réplicas/instâncias atrás de um load balancer — cada instância mantém seu próprio contador, então o limite efetivo multiplica pelo número de réplicas (ver seção "Rate limiting por IP" acima para o detalhe). Descartada a opção 3 (Redis) por YAGNI: não há necessidade atual de múltiplas instâncias; adicionar Redis agora seria infraestrutura para um requisito não presente.

**Decisão**: opção 2 — contador in-memory por IP + janela deslizante, como dependency FastAPI (`ip_rate_limiter.py`), aplicado só em `POST /auth/register`.

**Trade-offs**: proteção efetiva apenas em deploy single-instance; não é Unit of Work nem Port de domínio (rate limiting é proteção de infraestrutura HTTP, não regra de negócio) — vive inteiramente no adapter inbound.

**Impactos futuros**: se o projeto escalar para múltiplas réplicas, mover o contador para um store compartilhado (Redis, `INCR`+`EXPIRE` ou `GCRA`) é o upgrade natural — troca isolada na implementação da dependency, sem tocar rota ou use case.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Novo módulo `registration_use_cases.py` em vez de adicionar a `use_cases.py` existente | Mantém arquivos <500 linhas (regra do projeto) e separa fluxo público de admin | Um único arquivo cresceria além do razoável e misturaria dependências (Port `EmailSender`/`TokenGenerator` só usados aqui) com as de `001` |
| Tabela própria `email_verification_tokens` em vez de coluna em `users` | Reenvios geram múltiplos tokens ao longo do tempo; cooldown depende do mais recente | Coluna única não suporta histórico/cooldown sem perder o token anterior antes da janela de 24h expirar |
| Rate limiter in-memory por IP embutido na aplicação em vez de delegar a gateway | FR-014 exige implementação própria (decisão de `speckit-clarify`, não recomendação original) | Gateway externo ficaria fora do repositório/CI; Redis desde já seria infraestrutura para um requisito de múltiplas instâncias que não existe hoje (YAGNI) |
