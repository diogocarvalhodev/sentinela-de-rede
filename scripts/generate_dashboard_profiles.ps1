$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$basePath = Join-Path $root 'dashboards/nvr-dashboard.json'
$retailPath = Join-Path $root 'dashboards/nvr-dashboard-retail.json'
$industrialPath = Join-Path $root 'dashboards/nvr-dashboard-industrial.json'

if (-not (Test-Path $basePath)) {
  throw "Dashboard base nao encontrado: $basePath"
}

$base = Get-Content -Path $basePath -Raw -Encoding UTF8
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

$retail = $base
$retail = $retail -replace 'Monitoramento NVR - Escolas Municipais', 'Monitoramento de Seguranca - Operacao de Varejo'
$retail = $retail -replace 'NVRs', 'Gravadores'
$retail = $retail -replace 'NVR', 'Gravador'
$retail = $retail -replace 'C\\u00e2meras', 'Dispositivos'
$retail = $retail -replace 'c\\u00e2meras', 'dispositivos'
$retail = $retail -replace 'cameras', 'devices'
$retail = $retail -replace 'Escola', 'Loja'
$retail = $retail -replace 'escola', 'loja'
$retail = $retail -replace '"uid":\s*"[^"]*monitoring[^"]*"', '"uid": "retail-monitoring"'
[System.IO.File]::WriteAllText($retailPath, $retail, $utf8NoBom)

$industrial = $base
$industrial = $industrial -replace 'Monitoramento NVR - Escolas Municipais', 'Monitoramento Operacional - Ambientes Industriais'
$industrial = $industrial -replace 'NVRs', 'Gateways'
$industrial = $industrial -replace 'NVR', 'Gateway'
$industrial = $industrial -replace 'C\\u00e2meras', 'Sensores'
$industrial = $industrial -replace 'c\\u00e2meras', 'sensores'
$industrial = $industrial -replace 'cameras', 'sensors'
$industrial = $industrial -replace 'Escola', 'Unidade'
$industrial = $industrial -replace 'escola', 'unidade'
$industrial = $industrial -replace '"uid":\s*"[^"]*monitoring[^"]*"', '"uid": "industrial-monitoring"'
[System.IO.File]::WriteAllText($industrialPath, $industrial, $utf8NoBom)

Write-Output 'dashboards-generated'
