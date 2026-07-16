# Feature Specification: User CRUD API

**Feature Branch**: `001-user-crud-api`

**Created**: 2026-07-15

**Status**: Clarified (round 2 concluído com respostas reais do usuário em 2026-07-15 — ver seção Clarifications)

**Input**: User description: "API backend em Python com CRUD completo para cadastro de usuários (create, read, update, delete, list)"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Registrar novo usuário (Priority: P1)

Um cliente da API envia dados de um novo usuário (nome, email, senha) e o sistema cria o registro, rejeitando duplicatas de email e senhas fracas.

**Why this priority**: Sem criação não há cadastro; é o ponto de entrada de todo o domínio.

**Independent Test**: POST em `/users` com payload válido retorna 201 e o recurso criado (sem o hash de senha); repetir com mesmo email retorna 409.

**Acceptance Scenarios**:

1. **Given** nenhum usuário com o email X, **When** POST `/users` com dados válidos, **Then** sistema retorna 201 com o usuário criado (id, nome, email, timestamps) e nunca retorna a senha/hash.
2. **Given** um usuário já existe com email X, **When** POST `/users` com o mesmo email, **Then** sistema retorna 409 Conflict.
3. **Given** payload com email inválido ou senha abaixo da política mínima, **When** POST `/users`, **Then** sistema retorna 422 com detalhe do campo inválido.

---

### User Story 2 - Consultar usuário(s) (Priority: P1)

Um cliente consulta um usuário específico por id ou lista usuários cadastrados de forma paginada.

**Why this priority**: Leitura é indispensável para qualquer consumidor da API validar o cadastro; mesma criticidade da criação para um MVP de cadastro.

**Independent Test**: GET `/users/{id}` retorna o usuário; GET `/users` retorna lista paginada.

**Acceptance Scenarios**:

1. **Given** um usuário existente, **When** GET `/users/{id}`, **Then** sistema retorna 200 com os dados públicos do usuário.
2. **Given** id inexistente, **When** GET `/users/{id}`, **Then** sistema retorna 404.
3. **Given** N usuários cadastrados, **When** GET `/users?page=1&page_size=20`, **Then** sistema retorna página com metadados (total, page, page_size).
4. **Given** usuário logicamente excluído (soft-delete), **When** GET `/users/{id}` ou listagem, **Then** sistema retorna 404 / omite da listagem por padrão.

---

### User Story 3 - Atualizar cadastro (Priority: P2)

Um cliente atualiza dados de um usuário existente (nome, email; troca de senha via endpoint dedicado).

**Why this priority**: Necessário para manter o cadastro correto, mas depende de create/read já existirem.

**Independent Test**: PATCH `/users/{id}` com subconjunto de campos válidos atualiza somente os campos enviados e retorna 200.

**Acceptance Scenarios**:

1. **Given** usuário existente, **When** PATCH `/users/{id}` com novo nome, **Then** sistema atualiza somente o nome e retorna 200 com o recurso atualizado.
2. **Given** usuário existente, **When** PATCH `/users/{id}` com email já usado por outro usuário, **Then** sistema retorna 409.
3. **Given** id inexistente, **When** PATCH `/users/{id}`, **Then** sistema retorna 404.
4. **Given** usuário existente, **When** PATCH `/users/{id}/password` com nova senha válida (>=8 caracteres), **Then** sistema atualiza `password_hash` e `updated_at`, retorna 200 sem devolver a senha/hash.
5. **Given** usuário existente, **When** PATCH `/users/{id}/password` com senha abaixo da política mínima, **Then** sistema retorna 422.
6. **Given** id inexistente, **When** PATCH `/users/{id}/password`, **Then** sistema retorna 404.

---

### User Story 4 - Remover usuário (Priority: P3)

Um cliente remove (soft-delete) um usuário do cadastro.

**Why this priority**: Menos frequente que as demais operações; ainda assim faz parte do CRUD completo solicitado.

**Independent Test**: DELETE `/users/{id}` retorna 204; GET subsequente retorna 404.

**Acceptance Scenarios**:

1. **Given** usuário existente, **When** DELETE `/users/{id}`, **Then** sistema marca como excluído (soft-delete) e retorna 204.
2. **Given** id inexistente, **When** DELETE `/users/{id}`, **Then** sistema retorna 404.
3. **Given** usuário já excluído, **When** DELETE `/users/{id}` novamente, **Then** sistema retorna 404.

---

### Edge Cases

- Requisição concorrente de criação com mesmo email: apenas uma deve suceder (constraint UNIQUE no banco garante a corretude, não apenas checagem em aplicação).
- Payload malformado (JSON inválido, campos ausentes): 422 com corpo de erro estruturado e consistente entre endpoints.
- Paginação com `page`/`page_size` fora dos limites: aplicar limites e retornar 422 se inválidos, nunca 500.
- Requisição sem header de API key ou com key inválida/revogada: 401 em qualquer endpoint de `/users*`, sem vazar se a key existe e está só malformada vs. inexistente (mesma mensagem genérica).
- Troca de senha para o próprio valor atual: permitida (não é erro), sistema apenas re-hasheia.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Sistema MUST permitir criar um usuário com nome, email e senha, validando formato de email e política mínima de senha (mínimo 8 caracteres).
- **FR-002**: Sistema MUST rejeitar criação de usuário com email já cadastrado (ativo), retornando conflito (409).
- **FR-003**: Sistema MUST armazenar senha apenas como hash (nunca em texto plano), usando algoritmo de hashing adequado a senhas (não hash genérico).
- **FR-004**: Sistema MUST permitir consultar um usuário por identificador único, retornando 404 quando não existir ou estiver excluído.
- **FR-005**: Sistema MUST permitir listar usuários de forma paginada, com parâmetros de página e tamanho de página limitados a um máximo configurável.
- **FR-006**: Sistema MUST permitir atualização parcial (PATCH) de nome e email de um usuário existente, sem exigir reenvio de todos os campos.
- **FR-007**: Sistema MUST rejeitar atualização de email para um valor já usado por outro usuário ativo (409).
- **FR-008**: Sistema MUST permitir remoção de usuário via soft-delete (exclusão lógica), preservando o registro para auditoria/histórico.
- **FR-009**: Sistema MUST nunca retornar hash de senha ou qualquer segredo em nenhuma resposta da API.
- **FR-010**: Sistema MUST validar toda entrada nos limites do sistema (payload de requisição) antes de qualquer processamento de domínio, retornando 422 com detalhe do(s) campo(s) inválido(s).
- **FR-011**: Sistema MUST responder com um formato de erro consistente (mesma estrutura) em todos os endpoints para os mesmos tipos de falha (validação, não encontrado, conflito).
- **FR-012**: Sistema MUST expor identificador de usuário que não seja sequencial previsível (UUID), para evitar enumeração de recursos.
- **FR-013**: Sistema MUST permitir trocar a senha de um usuário existente via endpoint dedicado (`PATCH /users/{id}/password`), validando a mesma política mínima de senha do cadastro (FR-001) e nunca retornando a senha/hash na resposta.
- **FR-014**: Sistema MUST exigir autenticação do chamador (API key) em toda requisição a `/users*`, retornando 401 quando ausente ou inválida, antes de qualquer processamento de domínio.

### Key Entities *(include if feature involves data)*

- **User**: representa um cadastro de usuário. Atributos: id (UUID), nome, email (único entre usuários ativos), password_hash, created_at, updated_at, deleted_at (nulo se ativo). Nunca expõe password_hash em nenhuma serialização de saída.
- **API Key (config, não é entidade de domínio)**: credencial estática que identifica um cliente autorizado a chamar a API. Não modelada como tabela/CRUD nesta feature — ver Assumptions e ADR-004 em plan.md para a justificativa de escopo.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Todas as 5 operações de CRUD (create, read, update, delete, list) respondem em p95 < 200ms sob carga de até 50 req/s em ambiente de referência (single instância, banco local/rede próxima).
- **SC-002**: 100% das respostas de erro de validação seguem o mesmo formato estruturado (verificável via teste de contrato).
- **SC-003**: Nenhum teste automatizado ou revisão de código encontra senha/hash de senha em qualquer payload de resposta da API.
- **SC-004**: Criação concorrente de 2 usuários com mesmo email resulta em exatamente 1 sucesso e 1 conflito (verificável em teste de integração/concorrência).
- **SC-005**: 100% das requisições a `/users*` sem API key válida recebem 401 e nenhum dado de usuário é retornado (verificável via teste de contrato).

## Clarifications

### Sessão 2026-07-15 (round 1) — suposições provisórias do arquiteto (parcialmente substituídas no round 2)

- **Q: Exclusão é física ou lógica?** → A: Lógica (soft-delete). **Confirmado no round 2.**
- **Q: Verificação de email (double opt-in)?** → A: Não neste MVP; cadastro é imediato após validação de formato. **Confirmado no round 2.**
- **Q: Multi-tenancy?** → A: Não, único espaço de usuários. Não revisitado no round 2 (sem sinal de mudança).

### Round 2 (2026-07-15) — respostas reais do usuário

1. **Auth do chamador da API**: **PRECISA JÁ**, nesta entrega — não fica fora de escopo. Mecanismo escolhido: **API key** (ver ADR-004 em plan.md). Adiciona FR-013 (implementação) → renumerado FR-014, edge case de 401, SC-005.
2. **Exclusão de usuário**: **soft-delete confirmado** — sem mudança em relação ao round 1.
3. **Gestão de senha**: **endpoint de troca já no MVP** — não fica fora de escopo. Endpoint escolhido: `PATCH /users/{id}/password` (ver ADR-005 em plan.md e FR-013, User Story 3 cenários 4-6).
4. **Verificação de email**: cadastro imediato, sem double opt-in — **confirmado**, sem mudança.
5. **SLA/carga**: mantém meta de referência SC-001 (p95 < 200ms @ 50 req/s) — sem mudança, sem dado real de produção disponível ainda.

**Status**: Resolvido. Spec atualizada refletindo as respostas acima; nenhum bloco `[NEEDS CLARIFICATION]` pendente.

## Assumptions

- **API key autentica o cliente/serviço chamador, não o usuário final**: não há conceito de login/sessão de usuário nesta feature — quem tem uma API key válida pode operar sobre qualquer registro de `User` (mesmo modelo de autorização "flat" das demais operações CRUD). Login de usuário final fica fora de escopo (não solicitado).
- **Gestão de ciclo de vida da própria API key (emissão, rotação, revogação) não é modelada como CRUD nesta feature**: keys são configuradas via variável de ambiente (hashes pré-computados), não uma tabela com endpoints próprios — evita construir um segundo sistema de cadastro (de credenciais) quando o pedido foi CRUD de usuários. Revisar se múltiplos clientes precisarem de rotação self-service.
- **Troca de senha não exige senha atual**: como não há sessão de usuário final (API key é do chamador, não do usuário), o modelo de autorização é o mesmo já usado nas demais operações PATCH/DELETE — quem chama com API key válida pode trocar a senha de qualquer usuário, assim como pode editar nome/email. Não há fluxo de "esqueci minha senha" via email (consistente com "sem verificação de email").
- **Exclusão lógica (soft-delete)**, não física.
- **Sem multi-tenancy**: um único espaço de usuários.
- **Sem verificação de email** neste MVP.
- **Idioma/charset**: nome e email em UTF-8, sem validação de nacionalidade/formato de nome.
- **Volume esperado inicial**: baixo/médio (dezenas de milhares de usuários, dezenas de req/s).
- **Ambiente de execução**: serviço HTTP standalone, containerizável, sem infraestrutura legada (greenfield confirmado).
