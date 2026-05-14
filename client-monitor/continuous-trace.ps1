# Continuous detailed trace — runs in PowerShell window до Ctrl+C
# Каждые 5 sec probes 4 endpoints с detailed TLS/TCP stage info.
# Logs в trace.log. Captures EXACT failure stage when incident hits.
#
# Use: open PowerShell window, run: & 'D:\Projects\vps-monitor\client-monitor\continuous-trace.ps1'
# Leave window open. When site fails — screenshot + send timestamp.

$LogFile = 'D:\Projects\vps-monitor\client-monitor\trace.log'
$Targets = @(
    @{ Name = 'zavod';  Url = 'https://zavod.smm-ministr.ru/'  },
    @{ Name = 'survey'; Url = 'https://survey.smm-ministr.ru/' },
    @{ Name = 'brand';  Url = 'https://brand.smm-ministr.ru/'  },
    @{ Name = 'smm';    Url = 'https://krutly.com/'            }
)

Write-Host "Continuous trace started. Log: $LogFile"
Write-Host "Press Ctrl+C to stop."
Write-Host ""

while ($true) {
    $Timestamp = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    foreach ($t in $Targets) {
        $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
        $stage = 'unknown'
        $detail = ''
        try {
            $response = Invoke-WebRequest -Uri $t.Url -Method Head -TimeoutSec 8 -UseBasicParsing -ErrorAction Stop
            $stopwatch.Stop()
            $stage = "ok"
            $detail = "code=$($response.StatusCode)"
        } catch [System.Net.WebException] {
            $stopwatch.Stop()
            $stage = "NET_" + $_.Exception.Status.ToString()
            if ($_.Exception.Response) {
                $detail = "code=$([int]$_.Exception.Response.StatusCode)"
                $stage = "ok"
            } elseif ($_.Exception.InnerException) {
                $detail = "inner=$($_.Exception.InnerException.GetType().Name):$($_.Exception.InnerException.Message -replace ',', ';')"
            } else {
                $detail = "msg=$($_.Exception.Message -replace ',', ';' -replace '\r?\n', ' ')"
            }
        } catch {
            $stopwatch.Stop()
            $stage = "ERR_$($_.Exception.GetType().Name)"
            $detail = "msg=$($_.Exception.Message -replace ',', ';' -replace '\r?\n', ' ')"
        }
        $ms = [math]::Round($stopwatch.Elapsed.TotalMilliseconds)
        $line = "$Timestamp,$($t.Name),$stage,${ms}ms,$detail"
        Add-Content -Path $LogFile -Value $line -Encoding UTF8
        # Live console output — colorize good vs bad
        if ($stage -eq 'ok') {
            Write-Host "[$Timestamp] $($t.Name): $detail (${ms}ms)" -ForegroundColor Green
        } else {
            Write-Host "[$Timestamp] $($t.Name): $stage $detail (${ms}ms)" -ForegroundColor Red
        }
    }
    Start-Sleep -Seconds 5
}
