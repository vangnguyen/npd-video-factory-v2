$ErrorActionPreference = 'Stop'

$mainRepo = 'C:\Users\VANG NGUYEN\Documents\Codex\2026-08-20\referenced-chatgpt-conversation-this-is-an\work\npd-video-factory-v2'
$rcWorktree = 'C:\Users\VANG NGUYEN\Documents\Codex\2026-08-20\referenced-chatgpt-conversation-this-is-an\work\npd-video-factory-v2-rc3-op1'
$operationDir = 'C:\Users\VANG NGUYEN\Documents\Codex\2026-08-20\referenced-chatgpt-conversation-this-is-an\operation-acceptance'
$bundlePath = Join-Path $mainRepo 'docs\acceptance\v3-01\V3-01-GATE-RC3-OPENAI-VISION-A.json'
$assetPath = Join-Path $rcWorktree 'docs\acceptance\v3-01\assets\g03-a-owned-vision-test.png'
$authorityPath = Join-Path $operationDir 'V3-01-OPERATION-1-AUTHORITY.json'
$runnerPath = Join-Path $operationDir 'v3_01_operation1_runner.py'
$evidencePath = Join-Path $operationDir 'operation-1-result.json'
$secretFile = Join-Path $mainRepo '.env'

$expectedRcCommit = 'adde8d9c5a7f608db80cbd9d21aecd45f721065e'
$expectedMainCommit = 'a73bad37f1f3aa7c2347e6a76503246a46d3c112'
$expectedImageId = 'sha256:9339c880b48c8e3e57a8acfa2f9f692d553d316ac265f1133076ba4e99b3eb8a'
$expectedBundleHash = 'da4450ce9f3c6f2015d2fbea3af8ca2ffb108c13dd53daafdad294570ecf4d83'
$expectedAssetHash = 'a294fbe16817cef29447e43ff6d510edca01e055295da188d6b87663179c044e'
$expectedAuthorityHash = '7d50e8c8fc394ef0c98eb788646831a8e9e65a394fc7f78980e96db9a04dcd87'
$expectedRunnerHash = '4e47d81a1466543c0b3594cf969fe75533704622954ea0cd8574300b0e4b292b'
$expectedCiRun = '33175813324'
$validFrom = [DateTimeOffset]::Parse('2026-08-28T14:00:00Z')
$expiresAt = [DateTimeOffset]::Parse('2026-08-28T18:00:00Z')
$imageTag = 'npd-video-factory-v2:rc3-op1-adde8d9'
$postgresContainer = 'npd-vf-rc3-op1-postgres'
$runnerContainer = 'npd-vf-rc3-op1-runner'
$networkName = 'npd-vf-rc3-op1-net'

function Require-Condition([bool]$Condition, [string]$Code) {
    if (-not $Condition) {
        throw $Code
    }
}

function File-Hash([string]$Path) {
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

$now = [DateTimeOffset]::UtcNow
Require-Condition ($now -ge $validFrom -and $now -lt $expiresAt) 'ACCEPTANCE_WINDOW_INACTIVE'
Require-Condition (-not (Test-Path -LiteralPath $evidencePath)) 'EVIDENCE_ALREADY_EXISTS'
Require-Condition ([string]::IsNullOrWhiteSpace((docker ps -a --filter "name=^/$runnerContainer$" -q))) 'RUNNER_CONTAINER_ALREADY_EXISTS'

Require-Condition ((File-Hash $bundlePath) -eq $expectedBundleHash) 'GATE_BUNDLE_HASH_MISMATCH'
Require-Condition ((File-Hash $assetPath) -eq $expectedAssetHash) 'ASSET_HASH_MISMATCH'
Require-Condition ((File-Hash $authorityPath) -eq $expectedAuthorityHash) 'OPERATION_AUTHORITY_HASH_MISMATCH'
Require-Condition ((File-Hash $runnerPath) -eq $expectedRunnerHash) 'PYTHON_RUNNER_HASH_MISMATCH'

$mainHead = (git -C $mainRepo rev-parse HEAD).Trim()
$rcHead = (git -C $rcWorktree rev-parse HEAD).Trim()
$tagCommit = (git -C $mainRepo rev-list -n 1 vf-v3-01-rc3).Trim()
$remoteMain = (git -C $mainRepo ls-remote origin refs/heads/main).Split()[0].Trim()
Require-Condition ($mainHead -eq $expectedMainCommit -and $remoteMain -eq $expectedMainCommit) 'GOVERNANCE_MAIN_MISMATCH'
Require-Condition ($rcHead -eq $expectedRcCommit -and $tagCommit -eq $expectedRcCommit) 'RC3_RUNTIME_MISMATCH'
Require-Condition ([string]::IsNullOrWhiteSpace((git -C $mainRepo status --porcelain))) 'MAIN_WORKTREE_NOT_CLEAN'
Require-Condition ([string]::IsNullOrWhiteSpace((git -C $rcWorktree status --porcelain))) 'RC3_WORKTREE_NOT_CLEAN'

$image = (docker image inspect $imageTag | ConvertFrom-Json)[0]
Require-Condition ($image.Id -eq $expectedImageId) 'RUNTIME_IMAGE_ID_MISMATCH'
Require-Condition ($image.Config.Labels.'npd.video-factory.rc-commit' -eq $expectedRcCommit) 'RUNTIME_IMAGE_LABEL_MISMATCH'
Require-Condition ($image.Config.Labels.'npd.video-factory.purpose' -eq 'v3-01-operation-1') 'RUNTIME_IMAGE_PURPOSE_MISMATCH'

$postgres = (docker inspect $postgresContainer | ConvertFrom-Json)[0]
Require-Condition ($postgres.State.Status -eq 'running' -and $postgres.State.Health.Status -eq 'healthy') 'POSTGRES_NOT_HEALTHY'
Require-Condition ($postgres.RestartCount -eq 0) 'POSTGRES_RESTARTED'
Require-Condition ($null -eq $postgres.NetworkSettings.Ports.'5432/tcp') 'POSTGRES_PORT_PUBLISHED'
docker network inspect $networkName *> $null
Require-Condition ($LASTEXITCODE -eq 0) 'ACCEPTANCE_NETWORK_MISSING'

$ledgerCounts = (docker exec $postgresContainer psql -U video_factory -d video_factory -At -F '|' -c "SELECT (SELECT count(*) FROM provider_safety_operations),(SELECT count(*) FROM provider_safety_attempts),(SELECT count(*) FROM provider_safety_budget_days),(SELECT count(*) FROM provider_safety_circuits);").Trim()
Require-Condition ($ledgerCounts -eq '0|0|0|0') 'ACCEPTANCE_LEDGER_NOT_EMPTY'

$ci = gh run view $expectedCiRun --repo vangnguyen/npd-video-factory-v2 --json databaseId,headSha,status,conclusion,jobs | ConvertFrom-Json
Require-Condition ([string]$ci.databaseId -eq $expectedCiRun) 'EXACT_MAIN_CI_RUN_MISMATCH'
Require-Condition ($ci.headSha -eq $expectedMainCommit -and $ci.status -eq 'completed' -and $ci.conclusion -eq 'success') 'EXACT_MAIN_CI_NOT_GREEN'
Require-Condition (@($ci.jobs | Where-Object { $_.conclusion -ne 'success' }).Count -eq 0) 'EXACT_MAIN_CI_JOB_NOT_GREEN'

[ordered]@{
    verdict = 'PREFLIGHT_PASS'
    checked_at_utc = $now.ToString('o')
    rc_commit = $rcHead
    governance_main_commit = $mainHead
    exact_main_ci_run = $expectedCiRun
    ledger_counts = $ledgerCounts
    credential_loaded = $false
    api_calls_so_far = 0
} | ConvertTo-Json -Compress | Write-Output

$keyValue = ''
try {
    foreach ($line in [System.IO.File]::ReadLines((Resolve-Path -LiteralPath $secretFile))) {
        if ($line -match '^\s*OPENAI_API_KEY\s*=\s*(.+?)\s*$') {
            $keyValue = $Matches[1].Trim().Trim('"').Trim("'")
            break
        }
    }
    Require-Condition (-not [string]::IsNullOrWhiteSpace($keyValue)) 'CREDENTIAL_ALIAS_UNRESOLVED'

    $dockerArgs = @(
        'run', '--rm', '-i', '--name', $runnerContainer,
        '--network', $networkName,
        '--read-only',
        '--tmpfs', '/tmp:rw,noexec,nosuid,size=32m',
        '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges:true',
        '--pids-limit', '128',
        '--memory', '512m',
        '--cpus', '1',
        '--mount', "type=bind,source=$runnerPath,target=/runner.py,readonly",
        '--mount', "type=bind,source=$authorityPath,target=/authority.json,readonly",
        '--mount', "type=bind,source=$bundlePath,target=/gate.json,readonly",
        '--mount', "type=bind,source=$assetPath,target=/asset.png,readonly",
        '--mount', "type=bind,source=$operationDir,target=/evidence",
        '-e', 'GATE_BUNDLE_PATH=/gate.json',
        '-e', 'OPERATION_AUTHORITY_PATH=/authority.json',
        '-e', 'ASSET_PATH=/asset.png',
        '-e', 'EVIDENCE_PATH=/evidence/operation-1-result.json',
        '-e', 'DATABASE_URL=postgresql+asyncpg://video_factory:development-only@npd-vf-rc3-op1-postgres:5432/video_factory',
        '-e', "EXPECTED_OPERATION_AUTHORITY_SHA256=$expectedAuthorityHash",
        '-e', "EXPECTED_RUNTIME_COMMIT=$expectedRcCommit",
        '-e', 'EXPECTED_RUNTIME_TAG=vf-v3-01-rc3',
        '-e', "EXPECTED_GOVERNANCE_MAIN_COMMIT=$expectedMainCommit",
        '-e', "RUNTIME_IMAGE_ID=$expectedImageId",
        '-e', "EXACT_MAIN_CI_RUN_ID=$expectedCiRun",
        '-e', 'EXACT_MAIN_CI_CONCLUSION=success',
        $imageTag,
        'python', '/runner.py'
    )

    $runnerOutput = @($keyValue | & docker @dockerArgs)
    $runnerExitCode = $LASTEXITCODE
}
finally {
    $keyValue = $null
    [GC]::Collect()
}

$runnerOutput | Write-Output
exit $runnerExitCode
