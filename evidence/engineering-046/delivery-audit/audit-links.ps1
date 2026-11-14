Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$auditProject = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$auditEvidenceRoot = Join-Path $auditProject 'evidence/engineering-046'
$auditSources = [ordered]@{}
$auditLinks = [Collections.Generic.List[object]]::new()
$auditReferences = [Collections.Generic.HashSet[string]]::new()
foreach ($auditDocument in @('docs/COVERAGE_OFFICIAL.md', 'docs/ACCEPTANCE.md', 'docs/SUPPORT.md')) {
    $auditDocumentPath = Join-Path $auditProject $auditDocument
    $auditSources[$auditDocument] = (Get-FileHash -LiteralPath $auditDocumentPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $auditText = Get-Content -LiteralPath $auditDocumentPath -Raw
    foreach ($auditMatch in [regex]::Matches($auditText, '\[[^\]]+\]\(([^)]+)\)')) {
        $auditTarget = $auditMatch.Groups[1].Value
        if ($auditTarget.StartsWith('#') -or $auditTarget -match '^[a-zA-Z][a-zA-Z0-9+.-]*:') { continue }
        $auditRelative = [Uri]::UnescapeDataString(($auditTarget -split '#|\?', 2)[0])
        $auditResolved = [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $auditDocumentPath) $auditRelative))
        $auditLinks.Add([ordered]@{ document = $auditDocument; target = $auditTarget; exists = (Test-Path -LiteralPath $auditResolved) })
    }
}
function Find-AuditReferences($auditNode) {
    if ($auditNode -is [Collections.IDictionary]) {
        foreach ($auditItem in $auditNode.Values) { Find-AuditReferences $auditItem }
    } elseif ($auditNode -is [Collections.IEnumerable] -and $auditNode -isnot [string]) {
        foreach ($auditItem in $auditNode) { Find-AuditReferences $auditItem }
    } elseif ($auditNode -is [string] -and $auditNode -match '^(\.\./engineering-\d+/|(?:official-nf(?:248|265)|packaged-[^/]+|text-workspace|full-load-[^/]+|route-attempt-[^/]+|reload-input-attempts|python-tests|native-screenshot-input|delivery-audit|dist|build)/)') {
        [void]$auditReferences.Add($auditNode)
    }
}
$auditPlanPath = Join-Path $auditEvidenceRoot 'verification-plan.json'
$auditSources['evidence/engineering-046/verification-plan.json'] = (Get-FileHash -LiteralPath $auditPlanPath -Algorithm SHA256).Hash.ToLowerInvariant()
$auditPlan = Get-Content -LiteralPath $auditPlanPath -Raw | ConvertFrom-Json -AsHashtable
Find-AuditReferences $auditPlan
$auditEvidenceChecks = foreach ($auditReference in ($auditReferences | Sort-Object)) {
    $auditBase = if ($auditReference -match '^(build|dist)/') { $auditProject } else { $auditEvidenceRoot }
    [ordered]@{ reference = $auditReference; exists = (Test-Path -LiteralPath (Join-Path $auditBase $auditReference)) }
}
$auditMissingLinks = @($auditLinks | Where-Object { !$_.exists })
$auditMissingEvidence = @($auditEvidenceChecks | Where-Object { !$_.exists })
$auditReport = [ordered]@{
    timestamp = [DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(8)).ToString('o')
    passed = ($auditMissingLinks.Count -eq 0 -and $auditMissingEvidence.Count -eq 0)
    source_sha256 = $auditSources
    verification_plan_timestamp = $auditPlan.timestamp
    local_markdown_link_count = $auditLinks.Count
    local_markdown_links = $auditLinks.ToArray()
    evidence_reference_count = @($auditEvidenceChecks).Count
    evidence_references = @($auditEvidenceChecks)
    missing_markdown_links = $auditMissingLinks
    missing_evidence_references = $auditMissingEvidence
    metadata_note = 'SUPPORT/ACCEPTANCE Updated headers retain 2026-11-15T05:46:47.7460681+08:00. The sequential build was already complete when header-refresh authorization arrived; frozen delivery bytes were retained as requested.'
    limits = 'Read-only link existence snapshot bound to the recorded document/plan hashes. Root is updating the verification plan; this check does not certify later edits or test/runtime claim validity.'
}
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'links.audit.json'), ($auditReport | ConvertTo-Json -Depth 12) + "`n", [Text.UTF8Encoding]::new($false))
if (!$auditReport.passed) { throw 'Delivery documentation link audit failed; see links.audit.json' }
Write-Output "Read-only links passed: $($auditLinks.Count) Markdown links and $(@($auditEvidenceChecks).Count) evidence references"
