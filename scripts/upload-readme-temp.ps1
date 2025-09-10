Set-Location "C:\Users\jflema\OneDrive - Indra\Jonathan escritorio\Master Unir\TFM Jonathan Lema"

# Token obtenido previamente (pega aquí el token válido)
$TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbkBleGFtcGxlLmNvbSIsInJvbGVzIjpbImFkbWluIiwibW9kZXJhdG9yIiwiZXhwZXJ0IiwidXNlciJdLCJleHAiOjE3NTY1NzUzMzJ9.N1u77eyl4hseJ_2aEn-w7DZltBy0EZmwbCqOboj0fYE'

try {
    $file = Get-Item ".\README.md"
    if (-not $file) { Throw "README.md not found in repo root." }

    $bytes = [System.IO.File]::ReadAllBytes($file.FullName)
    $fname = $file.Name

    $handler = New-Object System.Net.Http.HttpClientHandler
    $client = New-Object System.Net.Http.HttpClient($handler)
    $client.DefaultRequestHeaders.Authorization = New-Object System.Net.Http.Headers.AuthenticationHeaderValue('Bearer',$TOKEN)

    $content = New-Object System.Net.Http.MultipartFormDataContent
    $fileContent = New-Object System.Net.Http.ByteArrayContent($bytes)
    $fileContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse('application/octet-stream')
    $content.Add($fileContent, 'f', $fname)

    $resp = $client.PostAsync('http://localhost:8102/files/upload', $content).Result
    $respBody = $resp.Content.ReadAsStringAsync().Result
    Write-Output "UPLOAD STATUS: $($resp.StatusCode)"
    Write-Output $respBody
} catch {
    Write-Output "UPLOAD ERROR: $($_.Exception.Message)"
    exit 1
}
