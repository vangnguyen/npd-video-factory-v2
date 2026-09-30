#!/usr/bin/env bash
# Install immutable host controls only. Does not create an activation, start the
# runner, read a provider credential, reserve budget, or dispatch a provider.
set -euo pipefail
set +x
umask 077
test "$(id -u)" = 0
source_root=/opt/npd-video-factory/runtime/source
runtime_root=/opt/npd-video-factory/runtime
config_root=/etc/npd-video-factory
unit_source="$source_root/deploy/executor"
script_source="$source_root/scripts"
hba=/etc/npd-video-factory/provider-custody/postgresql-16/pg_hba.conf
ident=/etc/npd-video-factory/provider-custody/postgresql-16/pg_ident.conf

test -d "$source_root/.git"
test "$(stat -c %U "$source_root")" = root
test -z "$(find "$source_root" -xdev \( -perm -0020 -o -perm -0002 \) -print -quit)"
getent passwd vf-executor >/dev/null
getent group vf-executor >/dev/null
getent passwd postgres >/dev/null
getent group postgres >/dev/null
test -f "$hba"
test -f "$ident"

install -d -o root -g root -m 0755 /run/npd-video-factory
install -d -o root -g root -m 0700 /var/lib/npd-video-factory/executor/secret-resolution
install -o root -g root -m 0755 "$script_source/provider-secret-resolver-installed.py" "$runtime_root/provider-secret-resolver.py"
install -o root -g root -m 0755 "$script_source/runtime-activation-installed.py" "$runtime_root/runtime-activation.py"
install -o root -g root -m 0755 "$source_root/apps/api/app/runtime_role_failsafe.py" "$runtime_root/runtime-role-failsafe.py"
install -o root -g root -m 0755 "$script_source/provider-execution-wrapper.sh" /usr/local/sbin/npd-vf-provider-execution
install -o root -g root -m 0440 "$unit_source/npd-vf-provider-execution.sudoers" /etc/sudoers.d/npd-vf-provider-execution
visudo -cf /etc/sudoers.d/npd-vf-provider-execution >/dev/null
install -o root -g root -m 0644 "$unit_source/npd-vf-secret-resolver.socket" /etc/systemd/system/npd-vf-secret-resolver.socket
install -o root -g root -m 0644 "$unit_source/npd-vf-secret-resolver.service" /etc/systemd/system/npd-vf-secret-resolver.service
install -o root -g root -m 0644 "$unit_source/npd-vf-runtime-role-failsafe.service" /etc/systemd/system/npd-vf-runtime-role-failsafe.service
install -o root -g root -m 0644 "$unit_source/npd-vf-runtime-role-failsafe.timer" /etc/systemd/system/npd-vf-runtime-role-failsafe.timer

# Exact system trust only; retain unrelated administrator entries, reject all
# wildcard trust, and collapse this canonical path to one entry.
cd /
git_system=(env -u GIT_DIR -u GIT_WORK_TREE git config --system)
if "${git_system[@]}" --get-all safe.directory 2>/dev/null | grep -Fxq '*'; then
  echo GIT_SAFE_DIRECTORY_WILDCARD_REJECTED
  exit 2
fi
"${git_system[@]}" --unset-all safe.directory "^${source_root}$" 2>/dev/null || true
"${git_system[@]}" --add safe.directory "$source_root"
test "$("${git_system[@]}" --get-all safe.directory | grep -Fxc "$source_root")" = 1

# Exact OS-to-DB peer mapping. No wildcard, trust, password, or TCP rule.
if ! grep -Fxq 'vf_executor_runtime_map vf-executor vf_executor_runtime' "$ident"; then
  printf '%s\n' 'vf_executor_runtime_map vf-executor vf_executor_runtime' >> "$ident"
fi
python3 - "$hba" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
raw = p.read_text()
old = "local   vf_provider_custody_v3_01                        vf_executor_runtime     peer"
new = "local   vf_provider_custody_v3_01   vf_executor_runtime     peer map=vf_executor_runtime_map"
if new not in raw:
    if raw.count(old) != 1:
        raise SystemExit("RUNTIME_HBA_BASELINE_MISMATCH")
    raw = raw.replace(old, new)
p.write_text(raw)
PY
chown root:postgres "$hba" "$ident"
chmod 0640 "$hba" "$ident"
systemctl reload npd-vf-provider-custody-postgresql.service
systemctl daemon-reload
systemctl enable --now npd-vf-runtime-role-failsafe.timer >/dev/null
systemctl disable --now npd-vf-secret-resolver.socket >/dev/null 2>&1 || true
"$runtime_root/venv/bin/python" -I "$runtime_root/runtime-activation.py" deactivate >/dev/null
echo EXECUTION_ACTIVATION_HOST_PROVISIONED_NO_AUTHORITY
