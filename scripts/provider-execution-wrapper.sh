#!/usr/bin/env bash
# Root-owned exact wrapper. Exec cleanup is mandatory on every child outcome.
set -uo pipefail
set +x
test "$(id -u)" = 0 || { echo RUNTIME_WRAPPER_ROOT_REQUIRED; exit 2; }
activation=/opt/npd-video-factory/runtime/runtime-activation.py
python=/opt/npd-video-factory/runtime/venv/bin/python
request=/opt/npd-video-factory/runtime/request.py
cleanup() {
  "$python" -I "$activation" deactivate >/dev/null
}
trap 'cleanup || true' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
"$python" -I "$activation" expire >/dev/null || exit 2
test "$("$python" -I "$activation" verify-nologin 2>/dev/null)" != RUNTIME_ROLE_NOLOGIN_VERIFIED || {
  echo RUNTIME_ACTIVATION_REQUIRED
  exit 2
}
runuser -u vf-executor -- env -i \
  PATH=/usr/local/bin:/usr/bin:/bin \
  WSL_DISTRO_NAME="${WSL_DISTRO_NAME:-}" \
  RUNNER_NAME="${RUNNER_NAME:-}" \
  GITHUB_REPOSITORY_OWNER="${GITHUB_REPOSITORY_OWNER:-}" \
  GITHUB_REPOSITORY="${GITHUB_REPOSITORY:-}" \
  GITHUB_EVENT_NAME="${GITHUB_EVENT_NAME:-}" \
  GITHUB_REF="${GITHUB_REF:-}" \
  GITHUB_WORKFLOW_REF="${GITHUB_WORKFLOW_REF:-}" \
  GITHUB_WORKFLOW_SHA="${GITHUB_WORKFLOW_SHA:-}" \
  VF_REQUEST_JSON="${VF_REQUEST_JSON:-}" \
  NPD_RUNTIME_DEACTIVATION_GUARD=ENFORCED \
  "$python" -I "$request"
status=$?
if ! cleanup; then
  trap - EXIT HUP INT TERM
  echo REVIEW_REQUIRED_RUNTIME_ROLE_STILL_ACTIVE
  exit 70
fi
trap - EXIT HUP INT TERM
exit "$status"
