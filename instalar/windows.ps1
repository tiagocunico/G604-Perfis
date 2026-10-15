# Instala o g604 no Windows: dependências Python + bandeja iniciando com o Windows.
#   powershell -ExecutionPolicy Bypass -File instalar\windows.ps1           instala
#   powershell -ExecutionPolicy Bypass -File instalar\windows.ps1 -Remover  tira da inicialização
param([switch]$Remover)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$atalho = Join-Path ([Environment]::GetFolderPath('Startup')) 'G604 Perfis.lnk'

if ($Remover) {
    if (Test-Path $atalho) { Remove-Item $atalho; "Removido da inicialização." } else { "Não estava na inicialização." }
    return
}

$python = (Get-Command python -ErrorAction Stop).Source
$pythonw = Join-Path (Split-Path $python) 'pythonw.exe'
& $python -m pip install --user -e "$repo[bandeja]"
if ($LASTEXITCODE -ne 0) { throw "pip falhou" }

$ws = New-Object -ComObject WScript.Shell
$l = $ws.CreateShortcut($atalho)
$l.TargetPath = $pythonw
$l.Arguments = '-m g604.bandeja'
$l.WorkingDirectory = $repo
$l.Description = 'Perfis do mouse G604'
$l.Save()
"Bandeja configurada para iniciar com o Windows: $atalho"

if (Get-Process lghub* -ErrorAction SilentlyContinue | Where-Object Name -ne 'lghub_updater') {
    Write-Warning 'O G Hub está aberto: feche-o (e tire da inicialização) para não brigar com o g604.'
}
"Para abrir agora: `"$pythonw`" -m g604.bandeja"
