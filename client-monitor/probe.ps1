# vps-monitor client-side probe
# Запускается через Task Scheduler каждую 1 минуту.
# Пишет в local CSV: D:\Projects\vps-monitor\client-monitor\client-probe-log.csv
#
# Когда Maxim видит outage — мы grep'нем log по timestamp и сравним с:
#   - RU YC vantage (logs/probes-ru.csv в репо)
#   - VPS internal health-check (/var/log/pleyada-health.log на VPS)
#
# Если client-log = FAIL + RU YC vantage = OK → проблема в Maxim'a network/VPN
# Если оба FAIL → real VPS/TSPU issue

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
            # 401/403/405 — сервер ответил, не outage, нормально
            $Results += "${key}=${code}/${ms}ms"
        } else {
            # Network-level error: ConnectFailure, NameResolutionFailure, ReceiveFailure, Timeout
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
