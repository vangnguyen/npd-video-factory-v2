#!/usr/bin/env bash
# One-time provisioning only. stdin is a short-lived repository registration
# token supplied by the orchestrator without printing it. NEVER enables or
# starts a runner. No custody, evidence, provider secrets or model networking.
set -euo pipefail
set +x
umask 077
test "$(id -u)" = 0
test "$#" = 1
hook_source="$1"
test -f "$hook_source"
test -f "$(dirname "$hook_source")/executor-job-started.sh"
runner_user=vf-executor
runner_home=/var/lib/npd-vf-runner
runner_root="$runner_home/runner"
config_root=/etc/npd-video-factory
# Refuse to overwrite any existing installation or account.
if getent passwd "$runner_user" >/dev/null || test -e "$runner_home" || test -e "$config_root"; then
  echo 'BLOCKED: executor installation already exists'
  exit 2
fi
IFS= read -r registration_token
test -n "$registration_token"
useradd --system --create-home --home-dir "$runner_home" --shell /usr/sbin/nologin "$runner_user"
chmod 700 "$runner_home"
install -d -m 755 "$config_root"
install -m 755 "$hook_source" "$config_root/job-started.py"
install -m 755 "$(dirname "$hook_source")/executor-job-started.sh" "$config_root/job-started.sh"
printf '%s\n' '{"approved_workflow_commits":[]}' > "$config_root/workflow-allowlist.json"
chmod 644 "$config_root/workflow-allowlist.json"
printf 'ENGAGED\n' > "$config_root/kill-switch"
chmod 644 "$config_root/kill-switch"
install -d -m 700 -o "$runner_user" -g "$runner_user" "$runner_root"
archive="$runner_home/runner.tar.gz"
curl --fail --silent --show-error --proto '=https' --tlsv1.2 --location \
  https://github.com/actions/runner/releases/download/v2.337.0/actions-runner-linux-x64-2.337.0.tar.gz \
  --output "$archive"
printf '%s  %s\n' 70920811a4f8ad4328818682bca5c6469c1c942fab52448868071d0063816613 "$archive" | sha256sum --check --status
chown "$runner_user:$runner_user" "$archive"
runuser -u "$runner_user" -- tar -xzf "$archive" -C "$runner_root"
cd "$runner_root"
# Runner CLI consumes ACTIONS_RUNNER_INPUT_TOKEN; no secret in argv or logs.
# Configuration diagnostics remain private in the runner home, not evidence.
if ! runuser -u "$runner_user" -- env ACTIONS_RUNNER_INPUT_TOKEN="$registration_token" \
  ./config.sh --unattended --url https://github.com/vangnguyen/npd-video-factory-v2 \
  --name npd-vf-vangnguyen-ubuntu --labels npd-video-factory,provider-execution \
  --work _work > "$runner_home/config-private.log" 2>&1; then
  unset registration_token
  echo 'BLOCKED: runner configuration failed; private host diagnostic retained'
  exit 2
fi
unset registration_token
# Root-owned admission configuration and files; the runner stays OFFLINE.
printf 'ACTIONS_RUNNER_HOOK_JOB_STARTED=%s/job-started.sh\n' "$config_root" > .env
chown root:root .env
chmod 644 .env
printf '%s\n' 'QUARANTINED: repository runner registered, no service installed or started; admission allowlist empty'
