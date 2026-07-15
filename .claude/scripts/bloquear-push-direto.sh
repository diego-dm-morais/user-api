#!/bin/bash
# .claude/scripts/bloquear-push-direto.sh
# Bloqueia git push executado diretamente pelo Bash.
# O push só deve acontecer através da skill /pre-push-review,
# que roda o gate de qualidade/QA/segurança antes de liberar.

echo "Bloqueado: use o comando /pre-push-review para rodar o gate de qualidade, QA e segurança antes do push." >&2
exit 2
