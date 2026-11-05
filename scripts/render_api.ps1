param(
    [ValidateSet("services", "service", "deploys", "deploy")]
    [string]$Action = "services",
    [string]$ServiceId = $env:RENDER_SERVICE_ID,
    [string]$CommitId = "",
    [int]$Limit = 20
)

$ErrorActionPreference = "Stop"

$key = $env:RENDER_API_KEY
if (-not $key) {
    $keyFile = Join-Path $env:TEMP "opencode\render_api_key.txt"
    if (Test-Path $keyFile) {
        $key = (Get-Content $keyFile -Raw).Trim()
    }
}
if (-not $key) {
    throw "RENDER_API_KEY is not set. Use `$env:RENDER_API_KEY or save the key to $env:TEMP\opencode\render_api_key.txt"
}

$headers = @{
    Authorization = "Bearer $key"
    Accept        = "application/json"
}
$base = "https://api.render.com/v1"

function Invoke-Render {
    param([string]$Method, [string]$Path, $Body = $null)
    $params = @{
        Method  = $Method
        Uri     = "$base$Path"
        Headers = $headers
    }
    if ($null -ne $Body) {
        $params.Body = ($Body | ConvertTo-Json -Depth 5)
        $params.ContentType = "application/json"
    }
    Invoke-RestMethod @params
}

switch ($Action) {
    "services" {
        $rows = Invoke-Render -Method "GET" -Path "/services?limit=$Limit"
        $rows | ForEach-Object {
            $s = $_.service
            [pscustomobject]@{
                id                = $s.id
                name              = $s.name
                type              = $s.type
                runtime           = $s.serviceDetails.runtime
                branch            = $s.branch
                autoDeployTrigger = $s.autoDeployTrigger
                suspended         = $s.suspended
                url               = $s.serviceDetails.url
            }
        }
    }
    "service" {
        if (-not $ServiceId) { throw "-ServiceId is required" }
        $s = (Invoke-Render -Method "GET" -Path "/services/$ServiceId").service
        [pscustomobject]@{
            id                = $s.id
            name              = $s.name
            type              = $s.type
            runtime           = $s.serviceDetails.runtime
            branch            = $s.branch
            autoDeployTrigger = $s.autoDeployTrigger
            suspended         = $s.suspended
            url               = $s.serviceDetails.url
            buildCommand      = $s.serviceDetails.envSpecificDetails.buildCommand
            startCommand      = $s.serviceDetails.envSpecificDetails.startCommand
        }
    }
    "deploys" {
        if (-not $ServiceId) { throw "-ServiceId is required" }
        $rows = Invoke-Render -Method "GET" -Path "/services/$ServiceId/deploys?limit=$Limit"
        $rows | ForEach-Object {
            $d = $_.deploy
            [pscustomobject]@{
                id         = $d.id
                status     = $d.status
                trigger    = $d.trigger
                commit     = $d.commit.id
                message    = $d.commit.message
                createdAt  = $d.createdAt
                finishedAt = $d.finishedAt
            }
        }
    }
    "deploy" {
        if (-not $ServiceId) { throw "-ServiceId is required" }
        $body = @{ clearCache = "do_not_clear" }
        if ($CommitId) { $body.commitId = $CommitId }
        $d = Invoke-Render -Method "POST" -Path "/services/$ServiceId/deploys" -Body $body
        [pscustomobject]@{
            id        = $d.id
            status    = $d.status
            trigger   = $d.trigger
            commit    = $d.commit.id
            createdAt = $d.createdAt
        }
    }
}
