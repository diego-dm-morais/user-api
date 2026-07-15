#!/bin/bash
# .claude/scripts/bloquear-push-direto.sh
# Bloqueia git push executado diretamente pelo Bash.
# O push só deve acontecer através da skill /pre-push-review,
# que roda o gate de qualidade/QA/segurança antes de liberar.
#
# Token de uso único: a skill, só depois de revisor+qa+cyber-sec aprovarem,
# cria .claude/.push-approved antes de chamar `git push`. Este hook consome
# (apaga) o token e libera; sem token, bloqueia. Isso evita que o próprio
# passo 4 da skill (o push real) seja bloqueado pelo hook que ela mesma exige.

MARKER=".claude/.push-approved"

if [ -f "$MARKER" ]; then
  rm -f "$MARKER"
  exit 0
fi

echo "Bloqueado: use o comando /pre-push-review para rodar o gate de qualidade, QA e segurança antes do push." >&2
exit 2
