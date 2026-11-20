# vps-monitor — external probes для VPS 186.246.14.127

Актуально20.11.2026: основной IP186.246.14.127, запасной186.246.14.113. Старый5.129.207.254 отключён. Новые строки main CSV содержат target_ip; старые строки без него относятся к прежнему IP. История CSV сохраняется, отказы прежнего адреса не относятся к текущему.

**Два независимых vantage point** пингуют 4 домена плеяды + SSH/443 порты VPS с целевым интервалом5минут (GitHub — best effort, возможны пропуски):

| Vantage | Где работает | Output | Cron |
|---|---|---|---|
| **GitHub Actions** | Microsoft Azure DC (US/EU) | `logs/probes.csv` | `2-59/5 * * * *` |
| **Yandex Cloud Function** | YC datacenters (РФ, ru-central1) | `logs/probes-ru.csv` | `0/5 * * * ? *` (Quartz) |

**Цель triangulation:** разделить гипотезы H1 (VPS down — оба vantage FAIL) vs H2 (RU-route blocked — RU FAIL, US OK) для diagnostic'а chat-id `infra-vps-stability-monitoring-01`.

## Логика triangulation (3 vantage points)

| VPS-internal `pleyada-health.log` | External GitHub Actions (US/EU) `probes.csv` | YC Function (RU) `probes-ru.csv` | Гипотеза |
|---|---|---|---|
| FAIL | FAIL | FAIL | **Сбой виден из трёх точек** — причина не установлена |
| OK | OK | FAIL | **Ошибка из РФ** — причина требует отдельной проверки |
| OK | FAIL | OK | **Ошибка из US/EU** — причина не установлена |
| OK | OK | OK | Норма |
| OK | FAIL | FAIL | Network upstream Timeweb или DNS issue |

**Note про HTTP коды:** GitHub Actions использует `curl GET` → 200 для всех endpoints. YC Function использует `urllib HEAD` → может вернуть 405 (Method Not Allowed) для FastAPI endpoints (uvicorn не поддерживает HEAD на default routes). **Для liveness важно различие `TIMEOUT/5xx vs anything else`** — 4xx означает что сервер отвечает = alive.

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

CSV формат новых строк: `TS,target_ip=186.246.14.127,zavod=HTTP,survey=HTTP,brand=HTTP,smm=HTTP,ssh22=OK|FAIL,tcp443=OK|FAIL`

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

## Yandex Cloud Function (RU vantage) — setup и operations

**Function:** `vps-monitor-ru` (id `d4esr5hbfer4196fdv0v` в folder `b1gte826dd4hvilbujvg`)
**Service Account:** `vps-monitor-fn` (id `aje08etfrr9mn6kmb32b`) — роль `serverless.functions.invoker`
**Trigger:** `vps-monitor-ru-5min` (id `a1spch1tl732gtdovj08`) — cron `0/5 * * * ? *`
**Source:** `yc-fn/index.py` (Python 3.12, stdlib only)
**Env vars:** `LOCKBOX_SECRET_ID` (ссылка на существующий секрет), `GITHUB_REPO=lukonin33/vps-monitor`, `VPS_CANDIDATE_IPS` (существующие отдельные проверки127/113/SPB). PAT функция читает сама из Lockbox; оператор не извлекает payload.

### Redeploy code (без потери env vars)

⚠ **YC Functions: каждая version имеет immutable env block.** CLI redeploy с `--environment FOO=bar` ПОЛНОСТЬЮ заменяет env (не merge). Без флага = empty env, GITHUB_TOKEN потерян.

**Правильный путь:**
1. Открыть https://console.cloud.yandex.ru/folders/b1gte826dd4hvilbujvg/functions/functions/d4esr5hbfer4196fdv0v
2. «Создать в редакторе» из последней version → upload code → save
3. UI копирует env из previous version automatically

**Текущий режим:** PAT уже находится в Lockbox, функция читает его сама. При выпуске нужно сохранить service account, все три environment-ссылки/настройки, runtime, timeout, memory и logging. Публикация исходника в GitHub сама по себе не обновляет функцию. Предыдущую версию сохранять с rollback-тегом; никаких новых секретов или прав для исправления IP не нужно.

### Cleanup / disable

```powershell
# Disable GitHub Actions workflow:
gh workflow disable vps-external-monitor.yml -R lukonin33/vps-monitor

# Disable YC RU function (через CLI):
& "C:\Users\lukon\yandex-cloud\bin\yc.exe" serverless trigger delete vps-monitor-ru-5min
& "C:\Users\lukon\yandex-cloud\bin\yc.exe" serverless function delete vps-monitor-ru
& "C:\Users\lukon\yandex-cloud\bin\yc.exe" iam service-account delete vps-monitor-fn

# Полное удаление repo:
gh repo delete lukonin33/vps-monitor --yes
```

## Cost

**GitHub Actions free tier** для private repo:
- 2000 min/month free
- Этот workflow: ~30 sec × 12 runs/hour × 24h × 30d = **~720 min/month** (≈36% бесплатной квоты)
- Public repo — unlimited

**Yandex Cloud Functions free tier:**
- 1M invocations/мес бесплатно
- Function execution time free до 10 GB-секунд/мес
- Этот function: 12 runs/hour × 24h × 30d = **8640 invocations/мес** (≈0.9% бесплатной квоты)
- Function memory 128 MB × ~3 sec avg execution = ~3.2 GB-секунд/run × 8640 = ~27600 GB-сек/мес (превышает 10000 free → ~17600 GB-сек paid × $0.000006 = ~$0.10/мес). При оптимизации до <1 sec execution — полностью в free tier.

## Pattern Pack reference

- **П3** — strict data contract в CSV (ровный формат, не silent fallback)
- **П6** — pipeline health metric из независимой vantage point
- **A2** — smoking-gun query first для confirmation H1/H2

---

**chat-id:** infra-vps-stability-monitoring-01
**task-id:** vps-stability-diagnostic-monitoring-2026-05-09
**created:** 2026-05-09
