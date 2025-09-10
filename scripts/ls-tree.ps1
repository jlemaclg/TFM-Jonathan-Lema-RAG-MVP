param([string]$Path=".")
Write-Host "Estructura de proyecto:"
Get-ChildItem -Path $Path -Recurse -Directory | Select-Object -ExpandProperty FullName
