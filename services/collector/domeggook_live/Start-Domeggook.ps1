[CmdletBinding(PositionalBinding=$false)]
param([switch]$Once,[switch]$Verify,[Alias('dry-run')][switch]$DryRun,[int]$Cycles=0,
      [Alias('discover-once')][switch]$DiscoverOnce,[Alias('discover-watch')][switch]$DiscoverWatch,
      [Alias('refresh-once')][switch]$RefreshOnce,[switch]$Watch,[switch]$Status,
      [string]$BackendConfig,[string]$Python='python',
      [Parameter(ValueFromRemainingArguments=$true)][string[]]$ExtraArguments)
foreach ($collectorFlag in $ExtraArguments) {
    switch ($collectorFlag) {
        '--discover-once' { $DiscoverOnce=$true }
        '--discover-watch' { $DiscoverWatch=$true }
        '--refresh-once' { $RefreshOnce=$true }
        '--watch' { $Watch=$true }
        '--once' { $Once=$true }
        '--dry-run' { $DryRun=$true }
        '--status' { $Status=$true }
        '--verify' { $Verify=$true }
        default { throw "Unsupported argument: $collectorFlag" }
    }
}
if (@($Once,$Verify,$DiscoverOnce,$DiscoverWatch,$RefreshOnce,$Watch,$Status | Where-Object { $_ }).Count -gt 1) {
    throw 'Select one execution mode.'
}
$collectorRepo=(Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$collectorArgs=@('-B','-m','services.collector.domeggook_live','--source','domeggook')
if ($Verify) { $collectorArgs+='--verify' } elseif ($Status) { $collectorArgs+='--status' }
elseif ($DiscoverOnce) { $collectorArgs+='--discover-once' } elseif ($DiscoverWatch) { $collectorArgs+='--discover-watch' }
elseif ($RefreshOnce) { $collectorArgs+='--refresh-once' } elseif ($Once) { $collectorArgs+='--once' }
else { $collectorArgs+='--watch' }
if ($DryRun) { $collectorArgs+='--dry-run' }
if ($Cycles -gt 0) { $collectorArgs+=@('--cycles',[string]$Cycles) }
if ($BackendConfig) { $collectorArgs+=@('--backend-config',(Resolve-Path -LiteralPath $BackendConfig).Path) }
Push-Location $collectorRepo
try { & $Python @collectorArgs; $collectorExit=$LASTEXITCODE } finally { Pop-Location }
exit $collectorExit
