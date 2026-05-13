# vps-monitor client-side probe (pure ASCII for PS 5.1 W-1251 compat)
# Runs every 1 min via Task Scheduler. Writes to local CSV.
# Used to triangulate client-side vs server-side outages.

$LogFile = 'D:\Projects\vps-monitor\client-monitor\client-probe-log.csv'
$Targets = [ordered]@{
    'zavod'  = 'https://zavod.smm-ministr.ru/'
    'survey' = 'https://survey.smm-ministr.ru/'
    'brand'  = 'https://brand.smm-ministr.ru/'
    'smm'    = 'https://krutly.com/'
}

$Timestamp = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$Results = @()

foreach ($key in $Targets.Keys) {
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $response = Invoke-WebRequest -Uri $Targets[$key] -Method Head -TimeoutSec 10 -UseBasicParsing -ErrorAction Stop
        $stopwatch.Stop()
        $code = $response.StatusCode
        $ms = [math]::Round($stopwatch.Elapsed.TotalMilliseconds)
        $Results += "${key}=${code}/${ms}ms"
    } catch [System.Net.WebException] {
        $stopwatch.Stop()
        $ms = [math]::Round($stopwatch.Elapsed.TotalMilliseconds)
        if ($_.Exception.Response) {
            $code = [int]$_.Exception.Response.StatusCode
            # 401/403/405 = server replied, auth/method issue, not outage
            $Results += "${key}=${code}/${ms}ms"
        } else {
            $status = $_.Exception.Status.ToString()
            $Results += "${key}=NET_${status}/${ms}ms"
        }
    } catch {
        $stopwatch.Stop()
        $ms = [math]::Round($stopwatch.Elapsed.TotalMilliseconds)
        $errType = $_.Exception.GetType().Name
        $Results += "${key}=ERR_${errType}/${ms}ms"
    }
}

$Line = "${Timestamp}," + ($Results -join ',')
Add-Content -Path $LogFile -Value $Line -Encoding UTF8
