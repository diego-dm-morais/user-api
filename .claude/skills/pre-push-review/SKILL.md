---
name: pre-push-review
description: >
  Roda o gate obrigatório de qualidade antes de um git push: aciona revisor,
  qa e cyber-sec em sequência, consolida os vereditos, aciona o bug-fix para
  corrigir achados quando autorizado, e só libera o push quando todos
  aprovarem. Invocado manualmente pelo usuário com /pre-push-review.
---

Você vai orquestrar o gate de pré-push. Siga esta sequência obrigatoriamente:

## 1. Executar os três agentes em sequência

Acione, nesta ordem, via delegação de subagente:

1. `revisor` — revisa as alterações que serão enviadas (qualidade, arquitetura, bugs).
2. `qa` — valida e executa a suíte de testes relevante às alterações.
3. `cyber-sec` — roda a revisão de segurança (vulnerabilidades, segredos expostos, scanners configurados no projeto).

Cada agente deve retornar um veredito explícito.

## 2. Política de aprovação

O push só pode prosseguir quando TODOS os agentes retornarem:

- ✅ aprovação plena, ou
- ⚠️ aprovação com ressalvas — desde que não haja nenhum achado Crítico ou Alto.

Bloquear imediatamente se qualquer agente retornar:

- ❌ reprovação (qualquer variação: "requer mudanças", "implementação incompleta", "suíte insuficiente", "requer correções de segurança");
- qualquer vulnerabilidade Crítica ou Alta;
- qualquer teste obrigatório falhando;
- erro de lint, type-check ou build definidos como obrigatórios pelo projeto.

## 3. Relatório consolidado

Antes de decidir, apresente ao usuário um resumo com:

- resultado do Code Review;
- resultado do QA;
- resultado da Segurança;
- quantidade de problemas por severidade;
- arquivos afetados;
- recomendações de correção.

## 4. Se aprovado

Crie o arquivo `.claude/.push-approved` (ex. `touch .claude/.push-approved`) imediatamente antes de rodar o push — é o token de uso único que o hook `bloquear-push-direto.sh` consome para liberar exatamente este push. Em seguida execute o `git push` real via Bash e confirme ao usuário.

## 5. Se bloqueado

1. Explique claramente o motivo do bloqueio e liste os problemas.
2. Pergunte ao usuário: "Foram encontrados problemas que impedem o push. Deseja que eu acione o bug-fix para corrigir automaticamente os que podem ser resolvidos com segurança?"
3. Se o usuário responder **sim**: acione o subagente `bug-fix`, passando a ele o relatório consolidado (achados, arquivos, testes falhando) como evidência real — nunca uma descrição vaga. O `bug-fix` diagnostica a causa raiz e aplica a menor correção possível, seguindo seu próprio fluxo de testes.
4. Depois que o `bug-fix` concluir, repita os passos 1–3 do zero (revisor, qa, cyber-sec de novo), e só faça o push se o novo ciclo aprovar integralmente.
5. Se o `bug-fix` não conseguir resolver algo, ou se o usuário responder **não**: mantenha o push bloqueado e encerre exibindo o relatório completo (incluindo o que o `bug-fix` já tentou, se for o caso) para correção manual.

## Regras inegociáveis

- Nenhum dos três agentes de checagem (revisor, qa, cyber-sec) pode ser pulado ou desabilitado.
- A correção de achados nunca é feita pela skill diretamente — sempre delegada ao subagente `bug-fix`, que segue seu próprio processo de causa raiz e validação por testes.
- Nunca faça o push se houver achado Crítico ou Alto pendente.
- Use sempre as ferramentas de lint, teste, scanner e type-check já configuradas no projeto (não invente novas).
- Seja transparente: mostre todas as verificações e seus resultados, mesmo quando aprovado.
