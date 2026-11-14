# SPDX-License-Identifier: Apache-2.0
param([string]$Node = 'node')

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -gt 7 -or
    ($PSVersionTable.PSVersion.Major -eq 7 -and $PSVersionTable.PSVersion.Minor -ge 3)) {
  $PSNativeCommandArgumentPassing = 'Legacy'
}

$installer = Join-Path $PSScriptRoot '..\..\install.ps1'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($installer, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Cannot parse install.ps1' }
$definition = $ast.Find({
  param($item)
  $item -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $item.Name -eq 'Test-NodeDir'
}, $true)
if (-not $definition) { throw 'Test-NodeDir not found' }
. ([scriptblock]::Create($definition.Extent.Text))

function Write-Log([string]$Text) { }
function Find-Cmd([string]$Name) {
  if ($Name -eq 'node') { return $script:NodeCommand }
  if ($Name -eq 'npm' -and $script:HasNpm) { return 'npm' }
  return $null
}
function FakeNode {
  $global:LASTEXITCODE = $script:FakeExitCode
  return $script:FakeVersion
}
function Assert-NodeCheck([bool]$Expected, [string]$Label) {
  if ((Test-NodeDir '') -ne $Expected) { throw "Node check failed: $Label" }
}

$script:HasNpm = $true
$script:NodeCommand = $Node
Assert-NodeCheck $true 'real Node 22+ with legacy native argument handling'
$script:NodeCommand = 'FakeNode'
$script:FakeExitCode = 0
$script:FakeVersion = 'v21.9.0'
Assert-NodeCheck $false 'Node older than 22'
$script:FakeVersion = 'invalid'
Assert-NodeCheck $false 'invalid version'
$script:FakeVersion = 'v22.1.0'
Assert-NodeCheck $true 'Node 22'
$script:FakeExitCode = 1
Assert-NodeCheck $false 'native command failure'
$script:FakeExitCode = 0
$script:HasNpm = $false
Assert-NodeCheck $false 'npm missing'
Write-Host 'Node version checks passed'
