# vps-monitor — external probe для VPS 5.129.207.254

GitHub Actions workflow, который каждые 5 минут пингует 4 домена плеяды + SSH/443 порты VPS со стороны GitHub runner'а (US/EU egress) и пишет CSV в `logs/probes.csv`.

**Цель:** разделить гипотезы H1 (VPS down) vs H2 (RU-route blocked) для diagnostic'а chat-id `infra-vps-stability-monitoring-01`.

## Логика разделения (cross-reference с VPS-internal /var/log/pleyada-health.log)

| VPS-internal log | External (этот workflow) | Maxim из РФ | Гипотеза |
|---|---|---|---|
| FAIL | FAIL | FAIL | **H1 — VPS реально down** (OOM / crash) |
| OK | OK | FAIL | **H2 — route from РФ blocked** (TSPU / провайдер) |
| OK | FAIL | FAIL | Network между GitHub и VPS / nginx local issue |
| OK | OK | OK | Норма |

## Setup (once, ~10 минут Maxim'у)

```powershell
# 1. (Уже сделано — папка существует на D:\Projects\vps-monitor\)

# 2. git init + commit
cd D:\Projects\vps-monitor
git init -b main
git add .
git commit -m "init: vps external monitor (every 5min)"

# 3. Создать private repo на GitHub через gh CLI
gh repo create lukonin33/vps-monitor --private --source=. --remote=origin --push

# Альтернатива (без gh CLI):
# - Зайти на github.com → New repository → "vps-monitor", private
# - git remote add origin git@github.com:lukonin33/vps-monitor.git
# - git push -u origin main

# 4. Включить Actions (по умолчанию вкл для новых private repo)
# Зайти https://github.com/lukonin33/vps-monitor/actions
# → workflow появится через ~5 мин (первый scheduled tick) ИЛИ нажать "Run workflow" вручную
```

## Что писать в `logs/probes.csv`

CSV формат: `TS,zavod=HTTP,survey=HTTP,brand=HTTP,smm=HTTP,ssh22=OK|FAIL,tcp443=OK|FAIL`

Пример:
```
2026-05-09T09:30:00Z,zavod=401,survey=200,brand=200,smm=200,ssh22=OK,tcp443=OK
```

- HTTP коды 200/3xx/401/403 = жив (401 ожидаемо у zavod из-за Basic Auth)
- 5xx / TIMEOUT = проблема
- ssh22/tcp443 = TCP reachability (sans auth)

## Cross-reference после incident'а

Когда Maxim видит «сайты не грузятся»:

```bash
# 1. Узнать timestamp incident'а (из памяти / скриншота / системных часов)
TS_INCIDENT="2026-05-09T18:05:00Z"   # пример

# 2. Посмотреть external view вокруг этого timestamp
ssh vps "grep -A 1 -B 1 \"$(echo $TS_INCIDENT | cut -dT -f1)T18:0\" /var/log/pleyada-health.log"

# 3. Cross-reference с этим repo (из локального Git)
cd D:\Projects\vps-monitor
git pull
grep "T18:0" logs/probes.csv | head -5
```

## Cleanup / disable

```powershell
# Disable workflow (но сохранить repo + история):
gh workflow disable vps-external-monitor.yml -R lukonin33/vps-monitor

# Полное удаление repo:
gh repo delete lukonin33/vps-monitor --yes
```

## Cost

GitHub Actions free tier для private repo:
- 2000 min/month free
- Этот workflow: ~30 sec × 12 runs/hour × 24h × 30d = **~720 min/month** (≈36% бесплатной квоты)
- Public repo — unlimited (можно перевести в public если CSV-логи не sensitive — они не sensitive, только http codes)

## Pattern Pack reference

- **П3** — strict data contract в CSV (ровный формат, не silent fallback)
- **П6** — pipeline health metric из независимой vantage point
- **A2** — smoking-gun query first для confirmation H1/H2

---

**chat-id:** infra-vps-stability-monitoring-01
**task-id:** vps-stability-diagnostic-monitoring-2026-05-09
**created:** 2026-05-09
