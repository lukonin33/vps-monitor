# Client-side monitor — Maxim's PC

Цель: capture **что видит твой browser** в моменты outage. Это даст 4-ю точку наблюдения в triangulation (помимо VPS internal + RU YC + GA US/EU).

## Установка (один раз, 2 минуты)

1. Открой **PowerShell** на твоём ПК (Win+X → Terminal/PowerShell)
2. Выполни:

```powershell
& 'D:\Projects\vps-monitor\client-monitor\install-task.ps1'
```

3. Должно появиться `=== Task installed ===` с подтверждением

Готово. Через 1 минуту начнёт писать в `client-probe-log.csv`.

## Что собирает

Каждую 1 минуту probes 4 сайта плеяды:
- `https://zavod.smm-ministr.ru/` (Контент-завод admin)
- `https://survey.smm-ministr.ru/` (Опросы)
- `https://brand.smm-ministr.ru/` (Бренд-министр)
- `https://krutly.com/` (Krutly production)

Пишет в `client-probe-log.csv` CSV-строку:
```
2026-05-13T15:33:41Z,zavod=401/120ms,survey=200/89ms,brand=200/95ms,smm=200/450ms
```

- **401/403/405** = сервер ответил (Basic Auth / Method Not Allowed) — нормально, не outage
- **200/2xx/3xx** = OK
- **NET_*** = network-level error (типа `NET_ConnectFailure`, `NET_NameResolutionFailure`, `NET_Timeout`) — **это real outage**
- **ERR_*** = другие исключения

## Что делать когда видишь outage

1. **Запиши timestamp** до минуты (или просто заметь время)
2. **Опционально** — выключи VPN на 2-3 минуты и попробуй снова. Если работает без VPN — issue в VPN. Если по-прежнему нет — issue в server / TSPU.
3. **Сообщи мне в чате** — я grep'ну client-log + сравню с RU YC vantage и VPS internal logs

## Сравнение через 1-2 дня

Через 24-48 часов мы будем иметь:
- ~1500 client probes (1/min × 24-48h)
- ~300 RU YC vantage probes (1/5min)
- ~700 VPS internal probes (1/2min)

Если когда client=FAIL **другие два OK** → это твой network/VPN
Если client=FAIL + RU=FAIL + VPS=OK → TSPU filter на VPS IP (route from РФ)
Если client=FAIL + RU=FAIL + VPS=FAIL → real VPS outage

## Stop task позже

```powershell
Unregister-ScheduledTask -TaskName 'vps-monitor-client-probe' -Confirm:$false
```

## Manual test без Task Scheduler

```powershell
& 'D:\Projects\vps-monitor\client-monitor\probe.ps1'
```

Один probe сейчас. Результат добавится в CSV.

## Privacy

- Log пишется **только локально** на твоём ПК (`D:\Projects\vps-monitor\client-monitor\client-probe-log.csv`)
- Не пушится никуда автоматически
- Содержит только HTTP коды + latency, ноль personally identifiable info
- `.gitignore` уже исключает client-probe-log.csv из commits
