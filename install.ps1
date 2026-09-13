param([string]$InstallDir = "$HOME/.codexpulse/project", [switch]$NoSkill)
$ErrorActionPreference = 'Stop'
foreach ($name in @('python', 'git', 'codex')) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        throw "Missing $name. Install Python 3.11+, Git, and Codex CLI, then run codex login."
    }
}
python -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required. Check Windows app execution aliases if python opens the Store.' }
if ($PSScriptRoot -and (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'codex_status.py'))) {
    $projectRoot = $PSScriptRoot
} else {
    $projectRoot = [IO.Path]::GetFullPath($InstallDir)
    if (Test-Path -LiteralPath $projectRoot) {
        throw "Destination already exists: $projectRoot. Run its codex_status.py --install or choose another InstallDir."
    }
    git clone --depth 1 https://github.com/NoobyGains/CodexPulse.git $projectRoot
    if ($LASTEXITCODE -ne 0) { throw 'Clone failed; no Codex configuration was changed.' }
}
python (Join-Path $projectRoot 'codex_status.py') --install
if ($LASTEXITCODE -ne 0) { throw 'Footer setup failed. See the diagnostic above.' }
if (-not $NoSkill) {
    python (Join-Path $projectRoot 'codex_status.py') --install-skill
    if ($LASTEXITCODE -ne 0) { throw 'Skill setup failed. The native footer is installed.' }
}
Write-Host "CodexPulse installed. Restart Codex for the footer."
Write-Host "Full display: python `"$projectRoot/codex_status.py`" --launch --cwd `"$PWD`""
