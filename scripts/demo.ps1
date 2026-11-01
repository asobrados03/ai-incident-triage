param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$Username = "",
    [string]$Password = ""
)

$ErrorActionPreference = "Stop"

$auth = @()
if ($Username -and $Password) {
    $loginPayload = @{ username = $Username; password = $Password } |
        ConvertTo-Json -Compress
    $login = curl.exe -sS -X POST "$BaseUrl/auth/login" `
        -H "Content-Type: application/json" `
        --data-raw $loginPayload | ConvertFrom-Json
    $auth = @("-H", "Authorization: Bearer $($login.access_token)")
}

Write-Host "1. Health"
curl.exe -sS "$BaseUrl/health"

Write-Host "`n2. Create incident"
$payload = @{
    title = "El panel no carga"
    description = "El panel devuelve un error al abrirlo."
    steps_to_reproduce = "Abrir el panel principal."
    expected_behavior = "Mostrar el panel."
    actual_behavior = "Se muestra un error."
    environment = "local"
    components = @("frontend")
} | ConvertTo-Json -Compress

$created = curl.exe -sS @auth -X POST "$BaseUrl/incidents" `
    -H "Content-Type: application/json" `
    --data-raw $payload | ConvertFrom-Json
$incidentId = $created.id
$created | ConvertTo-Json

Write-Host "`n3. Analyze"
$analyzed = curl.exe -sS @auth -X POST "$BaseUrl/incidents/$incidentId/analysis" |
    ConvertFrom-Json
$analyzed | ConvertTo-Json -Depth 10

Write-Host "`n4. Get incident"
curl.exe -sS @auth "$BaseUrl/incidents/$incidentId"

Write-Host "`n5. Human review"
$review = '{"severity":"high","review_comment":"Impacto confirmado en la revisión."}'
$reviewed = curl.exe -sS @auth -X PATCH "$BaseUrl/incidents/$incidentId/triage" `
    -H "Content-Type: application/json" `
    --data-raw $review | ConvertFrom-Json
$reviewed | ConvertTo-Json -Depth 10

Write-Host "`nDemo completed for incident $incidentId"
