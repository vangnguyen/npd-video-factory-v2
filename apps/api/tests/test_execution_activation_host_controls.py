from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_resolver_units_have_fixed_identity_socket_and_encrypted_credential():
    socket = read("deploy/executor/npd-vf-secret-resolver.socket")
    service = read("deploy/executor/npd-vf-secret-resolver.service")
    assert "ListenStream=/run/npd-video-factory/provider-secret-resolver.sock" in socket
    assert "SocketUser=root" in socket and "SocketGroup=vf-executor" in socket
    assert "SocketMode=0660" in socket and "Accept=no" in socket
    assert "User=root" in service and "Group=root" in service
    assert (
        "LoadCredentialEncrypted=openai-codex-video:"
        "/etc/credstore.encrypted/openai-codex-video"
    ) in service
    assert "RestrictAddressFamilies=AF_UNIX" in service
    # /run/npd-video-factory is shared with the custody PostgreSQL socket.
    # The resolver must not let systemd own/remove that shared parent.
    assert "RuntimeDirectory=npd-video-factory" not in service
    assert "ConditionPathExists=/etc/npd-video-factory/provider-secret-resolver-policy.json" in service
    assert "ConditionPathExists=/etc/npd-video-factory/provider-secret-resolver-policy.sha256" in service
    assert "Environment=OPENAI_API_KEY" not in service
    assert "systemd-creds decrypt" not in service


def test_root_wrapper_has_unconditional_cleanup_and_fixed_child():
    wrapper = read("scripts/provider-execution-wrapper.sh")
    assert "trap 'cleanup || true' EXIT" in wrapper
    assert "trap 'exit 129' HUP" in wrapper
    assert "trap 'exit 130' INT" in wrapper
    assert "trap 'exit 143' TERM" in wrapper
    assert '"$python" -I "$activation" deactivate' in wrapper
    assert "NPD_RUNTIME_DEACTIVATION_GUARD=ENFORCED" in wrapper
    assert '"$python" -I "$request"' in wrapper
    assert "eval " not in wrapper and "bash -c" not in wrapper
    sudoers = read("deploy/executor/npd-vf-provider-execution.sudoers")
    assert sudoers.rstrip().endswith(
        "vf-executor ALL=(root) NOPASSWD: /usr/local/sbin/npd-vf-provider-execution"
    )


def test_root_wrapper_uses_fixed_postgres_failsafe_preflight():
    wrapper = read("scripts/provider-execution-wrapper.sh")
    exact = "/usr/bin/systemctl start npd-vf-runtime-role-failsafe.service"
    assert exact in wrapper
    assert "RUNTIME_FAILSAFE_PREFLIGHT_FAILED" in wrapper
    assert '"$python" -I "$activation" expire' not in wrapper
    assert "$SYSTEMCTL" not in wrapper
    assert "${SYSTEMCTL" not in wrapper
    assert "${FAILSAFE_UNIT" not in wrapper
    assert wrapper.index(exact) < wrapper.index('"$python" -I "$activation" verify-nologin')
    assert wrapper.index('"$python" -I "$activation" verify-nologin') < wrapper.index(
        "runuser -u vf-executor"
    )


def test_root_wrapper_keeps_role_state_gate_separate_from_service_success():
    wrapper = read("scripts/provider-execution-wrapper.sh")
    assert "RUNTIME_ROLE_NOLOGIN_VERIFIED" in wrapper
    assert "RUNTIME_ACTIVATION_REQUIRED" in wrapper
    assert wrapper.index("RUNTIME_FAILSAFE_PREFLIGHT_FAILED") < wrapper.index(
        "RUNTIME_ACTIVATION_REQUIRED"
    )


def test_expiry_timer_and_exact_peer_map_provisioning_are_mandatory():
    timer = read("deploy/executor/npd-vf-runtime-role-failsafe.timer")
    service = read("deploy/executor/npd-vf-runtime-role-failsafe.service")
    provision = read("scripts/provision-execution-activation.sh")
    assert "OnUnitActiveSec=15s" in timer and "Persistent=true" in timer
    assert "User=postgres" in service and "Group=postgres" in service
    assert "runtime-role-failsafe.py expire" in service
    assert "runtime-activation.py expire" not in service
    assert "runuser" not in service and "sudo" not in service and " su " not in service
    assert "NoNewPrivileges=true" in service
    assert "ProtectSystem=strict" in service
    assert "RestrictAddressFamilies=AF_UNIX" in service
    assert "ReadWritePaths=" not in service
    assert "/etc/credstore.encrypted" in service
    assert "/var/lib/systemd/credential.secret" in service
    assert "disable --now npd-vf-secret-resolver.socket" in provision
    assert "vf_executor_runtime_map vf-executor vf_executor_runtime" in provision
    assert "peer map=vf_executor_runtime_map" in provision
    assert "safe.directory \"$source_root\"" in provision
    assert "safe.directory=*" not in provision
    assert "ALTER ROLE" not in provision  # lifecycle code owns the fixed SQL.
    assert (
        'install -o root -g root -m 0755 "$source_root/apps/api/app/runtime_role_failsafe.py" '
        '"$runtime_root/runtime-role-failsafe.py"'
    ) in provision
    root_activation = read("apps/api/app/runtime_activation_host.py")
    assert 'choices=("activate", "deactivate", "verify-nologin")' in root_activation
    assert "def expire(" not in root_activation


def test_execution_workflow_cannot_bypass_root_cleanup_wrapper():
    workflow = read(".github/workflows/video-factory-provider-execution.yml")
    assert "run: /usr/bin/sudo -n /usr/local/sbin/npd-vf-provider-execution" in workflow
    assert "/opt/npd-video-factory/runtime/request.py" not in workflow
