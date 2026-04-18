#!/usr/bin/env bash
# Настраивает репозиторий так, чтобы Release Please мог открывать PR релиза через GITHUB_TOKEN
# (без секрета RELEASE_PLEASE_TOKEN), если политика не переопределена на уровне org/enterprise.
#
# Требуется токен с правами на изменение настроек Actions репозитория:
#   - Classic PAT: scope `repo`
#   - Fine-grained: Repository administration — Read and write
#
# Использование:
#   export GITHUB_TOKEN=ghp_...   # или fine-grained PAT
#   ./scripts/configure-github-actions-release-automation.sh
#
# Документация: https://docs.github.com/en/rest/actions/permissions#set-default-workflow-permissions-for-a-repository

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TOKEN="${GITHUB_TOKEN:-${GITHUB_SETUP_TOKEN:-}}"
if [[ -z "$TOKEN" ]]; then
  echo "Укажите GITHUB_TOKEN или GITHUB_SETUP_TOKEN (PAT с правами repo / administration на репо)." >&2
  exit 1
fi

REMOTE_URL="$(git remote get-url origin 2>/dev/null || true)"
if [[ -z "$REMOTE_URL" ]]; then
  echo "Не найден git remote origin." >&2
  exit 1
fi

# https://github.com/owner/repo.git или git@github.com:owner/repo.git
if [[ "$REMOTE_URL" =~ github\.com[:/]([^/]+)/([^/.]+)(\.git)?$ ]]; then
  OWNER="${BASH_REMATCH[1]}"
  REPO="${BASH_REMATCH[2]}"
else
  echo "Не удалось разобрать owner/repo из: $REMOTE_URL" >&2
  exit 1
fi

API="https://api.github.com/repos/${OWNER}/${REPO}/actions/permissions/workflow"

echo "Текущие настройки workflow token (GET)…"
curl -sS -f \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer ${TOKEN}" \
  "$API" | python3 -m json.tool || true

echo
echo "Выставляю default_workflow_permissions=write и can_approve_pull_request_reviews=true (PUT)…"
HTTP_CODE="$(curl -sS -o /tmp/rp_workflow_resp.txt -w '%{http_code}' -X PUT \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer ${TOKEN}" \
  "$API" \
  -d '{"default_workflow_permissions":"write","can_approve_pull_request_reviews":true}')"

if [[ "$HTTP_CODE" == "204" ]]; then
  echo "OK (204). Проверьте Release Please: https://github.com/${OWNER}/${REPO}/actions/workflows/release-please.yml"
elif [[ "$HTTP_CODE" == "409" ]]; then
  echo "409 Conflict: настройки блокируются организацией/enterprise. Откройте политику на верхнем уровне (см. README)." >&2
  cat /tmp/rp_workflow_resp.txt >&2 || true
  exit 1
else
  echo "Ошибка HTTP $HTTP_CODE" >&2
  cat /tmp/rp_workflow_resp.txt >&2 || true
  exit 1
fi

echo
echo "Повторный GET…"
curl -sS -f \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer ${TOKEN}" \
  "$API" | python3 -m json.tool

echo
echo "Если workflow всё ещё пишет «not permitted to create or approve pull requests»,"
echo "откройте вручную: https://github.com/${OWNER}/${REPO}/settings/actions"
echo "и включите «Allow GitHub Actions to create and approve pull requests» (иногда только из UI)."
