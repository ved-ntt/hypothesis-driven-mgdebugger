# Windows PowerShell version of run_variant_a.sh (no mock backend here; use WSL for that).
#   .\scripts\run_variant_a.ps1 -Backend ollama -Dataset humaneval -MaxExamples 5
param(
  [Parameter(Mandatory)][ValidateSet("claude","mistral","vllm","ollama","openai")][string]$Backend,
  [Parameter(Mandatory)][ValidateSet("humaneval","mbpp","humanevalfix")][string]$Dataset,
  [int]$MaxExamples = 0
)
$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $PSScriptRoot
function Default($name, $value) { if (-not (Test-Path "env:$name")) { Set-Item "env:$name" $value } }
switch ($Backend) {
  "claude" { Default HDMG_BASE_URL "https://api.anthropic.com/v1/"; Default HDMG_MODEL "claude-haiku-5-5"; if (-not $env:HDMG_API_KEY) { $env:HDMG_API_KEY = (Get-Content "$Here\key\apikey.txt" -Raw).Trim() }; $env:HDMG_USE_MIN_P = "0"; $env:HDMG_TEMPERATURE = "none"; Default HDMG_PRICE_IN "0.10"; Default HDMG_PRICE_OUT "0.50"; Default HDMG_BUDGET_USD "1" }
  "mistral" { Default HDMG_BASE_URL "https://api.mistral.ai/v1"; Default HDMG_MODEL "codestral-latest"; if (-not $env:HDMG_API_KEY) { $env:HDMG_API_KEY = (Get-Content "$Here\key\mistral.txt" -Raw).Trim() }; $env:HDMG_USE_MIN_P = "0" }
  "vllm"   { Default HDMG_BASE_URL "http://localhost:18889/v1"; Default HDMG_MODEL "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct"; Default HDMG_API_KEY "token-abc123s"; Default HDMG_USE_MIN_P "1" }
  "ollama" { Default HDMG_BASE_URL "http://localhost:11434/v1"; Default HDMG_MODEL "deepseek-coder-v2:16b"; Default HDMG_API_KEY "ollama"; $env:HDMG_USE_MIN_P = "0" }
  "openai" { Default HDMG_BASE_URL "https://api.openai.com/v1"; Default HDMG_MODEL "gpt-4o-mini"; if (-not $env:HDMG_API_KEY) { throw "set HDMG_API_KEY" }; $env:HDMG_USE_MIN_P = "0" }
}
$Seeds = @{ humaneval = "input_data/humaneval/seed/deepseekcoder/seed.jsonl"; mbpp = "input_data/mbpp/seed/deepseekcoder/seed.jsonl"; humanevalfix = "input_data/humanevalfix/seeds.jsonl" }[$Dataset]
Default HDMG_STOP_ON "both"
Push-Location "$Here\MGDebugger\src"
try {
  if ($MaxExamples -gt 0) { python main.py --seeds $Seeds --max-examples $MaxExamples } else { python main.py --seeds $Seeds }
  $RunDir = Get-ChildItem -Recurse -Directory output_data | Where-Object { $_.Name -match '^\d{8}-\d{6}$' } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  python "$Here\scripts\summarize.py" $RunDir.FullName | Tee-Object "$($RunDir.FullName)\summary.txt"
} finally { Pop-Location }
