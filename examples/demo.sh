#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
export ORQUESTA_ACTOR="${ORQUESTA_ACTOR:-demo}"
export GIT_AUTHOR_NAME=demo GIT_AUTHOR_EMAIL=demo@example.com GIT_COMMITTER_NAME=demo GIT_COMMITTER_EMAIL=demo@example.com
run() { "${ORQUESTA_BIN:-orquesta}" "$@"; }

cp -r "$here/workspace" "$work/workspace"
git -C "$work/workspace" init -q -b main
git -C "$work/workspace" add -A
git -C "$work/workspace" commit -q -m "workspace de ejemplo"
git -C "$work/workspace" update-ref refs/remotes/origin/main HEAD
for repo in shop-web payments-api infra-gitops; do
  mkdir -p "$work/workspace/$repo"
  git -C "$work/workspace/$repo" init -q -b main
  git -C "$work/workspace/$repo" commit -q --allow-empty -m "$repo"
done
sha="$(git -C "$work/workspace" rev-parse HEAD)"

echo "== registro"
run registry list --workspace "$work/workspace" --sha "$sha"

echo "== política: escribir en infra-gitops y en shop-web"
for repo in infra-gitops shop-web; do
  printf '{"tool_name": "Write", "tool_input": {"file_path": "%s/%s/a.txt"}, "cwd": "%s"}' "$work/workspace" "$repo" "$work/workspace" |
    run policy eval --hook --workspace "$work/workspace" --sha "$sha"
  echo "  ($repo evaluado)"
done

echo "== evaluación de ruteo con el proveedor de prueba"
run eval run --workspace "$work/workspace" --suite evals/routing/cases.yaml --sha "$sha" \
  --provider fake --answers "$here/answers.yaml" | python3 -c 'import json, sys; print(json.dumps(json.load(sys.stdin)["metrics"], indent=2))'
