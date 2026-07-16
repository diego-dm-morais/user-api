# Feature Specification: Self-Service User Registration

**Feature Branch**: `002-user-registration`

**Created**: 2026-07-15

**Status**: Clarificado — 5 pontos resolvidos via `speckit-clarify` em 2026-07-15 (ver `## Clarifications`). Pronto para `speckit-plan`/ajuste de plano e depois `speckit-tasks`.

**Input**: "Desenhar cadastro de usuário (self-service signup)" — distinto do `POST /users` já existente em `001-user-crud-api`.

## Relação com 001-user-crud-api

`001` já implementa `POST /users`, mas é uma operação **administrativa**: protegida por API key de serviço-a-serviço, sem verificação de email, senha definida por quem chama a API (não necessariamente pelo próprio usuário), conta ativa imediatamente (ver Assumptions/ADR-004/ADR-005 de `001/plan.md`). Não é self-signup.

Esta feature (`002`) cobre o caso **(a)**: um visitante anônimo (sem API key, sem sessão prévia) cria a própria conta, define a própria senha, e a conta exige confirmação de posse do email antes de ficar utilizável — fluxo público, diferente do CRUD administrativo. `001` permanece intacto (uso administrativo/interno continua existindo em paralelo).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Cadastro público (Priority: P1)

Um visitante anônimo envia nome, email e senha própria para `POST /auth/register` (sem API key) e recebe confirmação de que o cadastro foi iniciado; a conta fica `pending` até confirmar o email.

**Independent Test**: POST `/auth/register` com payload válido retorna 202 (aceito, pendente de confirmação) sem autenticação prévia; conta não aparece como ativa em `GET /users/{id}` (endpoint administrativo de `001`) até confirmação — ou aparece com um campo `email_verified: false`.

**Acceptance Scenarios**:

1. **Given** nenhum usuário com o email X, **When** POST `/auth/register` com dados válidos, **Then** sistema cria usuário em estado pendente, dispara email de confirmação, retorna 202 com mensagem genérica (não revela se o cadastro foi de fato novo — ver US3).
2. **Given** payload com email inválido ou senha abaixo da política mínima (>=8 caracteres, mesma regra de `001`), **When** POST `/auth/register`, **Then** sistema retorna 422.

---

### User Story 2 - Confirmar email (Priority: P1)

O usuário clica no link recebido por email (`GET /auth/confirm?token=...`) e a conta passa a `active`.

**Independent Test**: token válido e não expirado ativa a conta e retorna 200; reuso do mesmo token retorna 410/409.

**Acceptance Scenarios**:

1. **Given** token de confirmação válido e não expirado, **When** GET `/auth/confirm?token=X`, **Then** sistema marca `email_verified_at`, retorna 200.
2. **Given** token expirado, inválido, inexistente ou já usado (qualquer uma das quatro condições), **When** GET `/auth/confirm?token=X`, **Then** sistema retorna sempre **400** com mensagem genérica sugerindo solicitar novo envio — mesmo status/corpo nas quatro condições, sem revelar qual delas ocorreu (FR-011).

---

### User Story 3 - Reenviar confirmação (Priority: P2)

Usuário que não recebeu ou perdeu o email solicita novo envio.

**Acceptance Scenarios**:

1. **Given** conta pendente existente, **When** POST `/auth/register/resend` com o email, **Then** sistema invalida token anterior, gera novo, envia novo email, retorna 202.
2. **Given** cooldown ativo (< 60s desde o último envio para o mesmo email), **When** novo pedido de reenvio, **Then** sistema retorna 429.
3. **Given** email não cadastrado ou já confirmado, **When** POST `/auth/register/resend`, **Then** sistema retorna 202 com a mesma mensagem genérica de US1.2 (evita enumeração de contas existentes).

---

### Edge Cases

- **Email já cadastrado e ativo**: `POST /auth/register` retorna 202 genérico (não 409) — não revela existência da conta a um chamador anônimo; efeito colateral real é nenhum (não recria, não reenvia nada). Trade-off documentado no ADR-002.
- **Email já cadastrado mas ainda pendente (não confirmado)**: novo `POST /auth/register` para o mesmo email reemite um novo token de confirmação (equivalente a US3), **sujeito ao mesmo cooldown de 60s de FR-009** (se dentro do cooldown, não reemite, mas ainda retorna 202 genérico — ver FR-010, este caminho não tem a exceção 429 que `/resend` tem); senha enviada no novo POST **não substitui** a anterior (evita que um atacante sem posse do email sobrescreva a senha de uma conta pendente de terceiro).
- **Rate limiting de tentativas**: cooldown de 60s por email entre envios de confirmação (US3.2); adicionalmente, `POST /auth/register` MUST aplicar rate limit por IP implementado na própria aplicação (não delegado a gateway) — ver FR-014.
- **Token expirado**: janela de 24h; usuário deve solicitar reenvio (US3).
- **Conta pendente nunca confirmada**: permanece indefinidamente como está (sem expurgo automático nesta versão — ver Assumptions).
- **Senha fraca**: mesma política de `001` (mínimo 8 caracteres), 422.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Sistema MUST permitir que um visitante anônimo (sem autenticação prévia) crie uma conta com nome, email e senha própria via `POST /auth/register`.
- **FR-002**: Sistema MUST validar formato de email e política mínima de senha (>=8 caracteres) antes de qualquer processamento, retornando 422 em caso de falha.
- **FR-003**: Sistema MUST armazenar a senha apenas como hash (mesmo Port `PasswordHasher`/argon2id de `001`).
- **FR-004**: Sistema MUST criar a conta em estado `pending` (não utilizável até confirmação de email).
- **FR-005**: Sistema MUST gerar um token de confirmação de alta entropia, associá-lo à conta pendente, e enviá-lo via Port `EmailSender` antes de a conta ficar ativa. Adapter concreto da v1: log/console (sem envio real de email); adapter de produção (SMTP/provedor transacional) fica para versão futura, quando o provedor estiver definido — ver Assumptions.
- **FR-006**: Sistema MUST expirar o token de confirmação 24h após emissão.
- **FR-007**: Sistema MUST ativar a conta (`email_verified_at` preenchido) somente mediante apresentação de token válido, não expirado e ainda não usado.
- **FR-008**: Sistema MUST invalidar o token após uso (não reutilizável).
- **FR-009**: Sistema MUST permitir reenvio de confirmação para uma conta pendente, respeitando cooldown mínimo de 60s entre envios para o mesmo email. Cooldown aplica-se igualmente ao caminho de reemissão via `POST /auth/register` (email já pendente) e via `POST /auth/register/resend` — mesma checagem, ambos os endpoints, para não permitir bypass do rate limit por email trocando de endpoint.
- **FR-010**: Sistema MUST responder de forma genérica e idêntica (mesmo status/corpo) a `POST /auth/register` e `POST /auth/register/resend` independente de o email já existir (ativo, pendente ou inexistente), para não permitir enumeração de contas por um chamador anônimo. **Exceção documentada e aceita**: quando o cooldown de reenvio (FR-009) está ativo para uma conta pendente existente, a resposta é **429** em vez do 202 genérico — esse é o único caso em que o status pode diferir. É um trade-off aceito (rate-limiting de abuso de envio, não enumeração deliberada de contas): um 429 sinaliza só que *se* aquele email tiver conta pendente, houve uma tentativa recente — não confirma que a conta existe (um chamador não sabe se um eventual 202 seguinte é porque o cooldown expirou ou porque nunca existiu conta). Risco residual assumido conscientemente, não corrigido nesta versão.
- **FR-011**: Sistema MUST rejeitar confirmação com token inválido, expirado ou já usado, sem revelar qual dessas três condições ocorreu.
- **FR-012**: Sistema MUST nunca retornar hash de senha, token em texto plano (fora do email) ou qualquer segredo em resposta HTTP.
- **FR-013**: Sistema MUST reusar a entidade `User` e sua constraint de unicidade de email (ativos) já existentes em `001`, sem duplicar o conceito de usuário.
- **FR-014**: Sistema MUST aplicar rate limiting por IP em `POST /auth/register`, implementado na própria aplicação (sem depender de gateway externo). Limite exato (ex.: N req/min por IP) e mecanismo de contagem (in-memory single-instance vs. store compartilhado) são decisão de `plan.md`.
- **FR-015**: `GET /users` e `GET /users/{id}` (endpoints administrativos de `001`) MUST expor o campo `email_verified: boolean` na resposta, refletindo se `email_verified_at` está preenchido.

### Key Entities *(include if feature involves data)*

- **User** (reused de `001`): ganha o atributo `email_verified_at: datetime | None`. `None` = pendente/não confirmado.
- **EmailVerificationToken** (novo): id, user_id, token_hash (nunca o token em claro), created_at, expires_at, used_at (nulo se ainda válido). Tabela própria (não coluna única em `User`) porque reenvios geram múltiplos tokens ao longo do tempo e o histórico/limite de cooldown depende de `created_at` do mais recente.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% das respostas de `POST /auth/register` e `POST /auth/register/resend` são indistinguíveis (mesmo status/corpo) entre email novo, email pendente e email já ativo, **exceto** quando cooldown de reenvio está ativo (429, exceção documentada em FR-010) (verificável via teste de contrato) — FR-010.
- **SC-002**: Nenhum teste ou revisão encontra hash de senha ou token em claro em qualquer resposta HTTP.
- **SC-003**: Confirmação com token expirado (>24h) é rejeitada em 100% dos casos testados.
- **SC-004**: Reuso do mesmo token de confirmação é rejeitado na segunda tentativa em 100% dos casos testados.
- **SC-005**: Duas tentativas de reenvio para o mesmo email em menos de 60s resultam em exatamente 1 email efetivamente enviado (a segunda retorna 429).
- **SC-006**: Requisições de `POST /auth/register` acima do limite de IP configurado retornam 429 em 100% dos casos testados (FR-014).
- **SC-007**: `GET /users`/`GET /users/{id}` retornam `email_verified: true` para conta confirmada e `false` para conta pendente em 100% dos casos testados (FR-015).

## Clarifications

### Session 2026-07-15

- Q: Confirmação de email é obrigatória antes da conta ficar utilizável? → A: Sim, obrigatória (recomendação aceita) — ver FR-004/FR-007.
- Q: Qual adapter de envio de email na v1? → A: Log/console apenas em dev — sem envio real de email na v1; adapter de produção (SMTP/provedor) fica para versão futura, quando o provedor estiver definido (ver FR-005, Assumptions).
- Q: Rate limiting de `POST /auth/register` por IP entra no escopo desta feature? → A: Sim, implementação própria na aplicação (não delegado a gateway) — ver FR-014, SC-006.
- Q: Conta pendente nunca confirmada deve expirar/ser limpa automaticamente? → A: Não nesta versão, sem job de expurgo (recomendação aceita).
- Q: `GET /users`/`GET /users/{id}` (endpoints admin de `001`) devem expor `email_verified`? → A: Sim, adicionar campo booleano (recomendação aceita) — ver FR-015, SC-007.

## Assumptions

- Login de usuário final continua fora de escopo (mesma assunção de `001`); esta feature apenas cria e confirma a conta, não autentica sessões.
- Endpoints `/auth/*` são públicos (sem `verify_api_key`); distintos de `/users*` (protegidos por API key, `001`).
- Volume e SLA seguem a mesma referência de `001` (SC-001 de `001/spec.md`), sem dado real de produção específico para registro público.
- Envio de email é *fire-and-forget* do ponto de vista da resposta HTTP (202 Accepted): falha no envio não deve reverter a criação da conta pendente nem vazar detalhe de infraestrutura ao chamador — é retentável via US3 (resend).
- Adapter de email da v1 é log/console (nenhum provedor de produção contratado ainda); trocar para SMTP/provedor transacional real é apenas questão de novo adapter atrás do Port `EmailSender` existente, sem mudar domain/application.
- Rate limit por IP (FR-014) é responsabilidade da própria aplicação nesta versão, não de gateway externo; implementação de referência: contador in-memory por IP com janela deslizante, single-instance (não compartilhado entre réplicas) — suficiente para deploy de instância única; se a aplicação escalar horizontalmente, mover para store compartilhado (ex.: Redis) é o upgrade natural.
