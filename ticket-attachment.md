# Приложение к тикету Timeweb support

**VPS:** 5.129.207.254, тариф Cloud NSK 40, hostname `nsk-1-vm-nz9b`, нода `kvmnvm-841`
**Дата:** 2026-05-11
**Public dashboard:** https://monitor.smm-ministr.ru/dashboard/
**Public repo с raw данными:** https://github.com/lukonin33/vps-monitor

---

## 1. Симптомы

С разных устройств в РФ-сети (МТС, Билайн, Wi-Fi разных провайдеров) периодически наблюдаются:

- TLS handshake timeout для всех HTTPS-сайтов на VPS:
  - `zavod.smm-ministr.ru`
  - `survey.smm-ministr.ru`
  - `brand.smm-ministr.ru`
  - `krutly.com`
- `kex_exchange_identification: read: Connection reset by peer` при SSH-подключениях
- Восстановление само через несколько минут (~5)
- Помогает обход через VPN другой страны → подозрение на сетевую фильтрацию или peering issue на RU-стороне

## 2. Methodology — multi-vantage monitoring

Для воспроизведения и фиксации timestamps развёрнут multi-vantage мониторинг:

| Vantage | Где работает | Cadence | Логи |
|---|---|---|---|
| **VPS-internal** | health-check cron на самом VPS | каждые 2 мин | `/var/log/pleyada-health.log` |
| **External US/EU** | GitHub Actions (Microsoft Azure DC, US Virginia / EU Ireland) | каждые 5 мин | https://github.com/lukonin33/vps-monitor/blob/main/logs/probes.csv |
| **External RU** | Yandex Cloud Function (ru-central1, Новосибирск) | каждые 5 мин | https://github.com/lukonin33/vps-monitor/blob/main/logs/probes-ru.csv |

Логи в формате CSV доступны публично без авторизации (repo public, GitHub Pages).

## 3. Concrete incident — 2026-05-10 18:06:14 UTC

| Vantage | Время (UTC) | Состояние |
|---|---|---|
| RU (Yandex Cloud ru-central1) | 18:01:13 | Все 4 сайта OK + TCP 22 OK + TCP 443 OK |
| **RU (same vantage)** | **18:06:14** | **TIMEOUT для всех 4 HTTPS + TCP 22 = FAIL + TCP 443 = FAIL** |
| US/EU (GitHub Actions) | **18:09:04** (3 мин после RU FAIL) | **Все 4 сайта OK + TCP 22 OK + TCP 443 OK** |
| RU (same vantage) | 18:11:11 | Восстановление: всё OK |

**Интерпретация:** в момент когда RU vantage не мог установить TCP-соединение к 5.129.207.254 на портах 22 и 443, US/EU vantage через 3 минуты в том же временном окне видел VPS полностью доступным. Значит **VPS физически не падал** (работал для не-РФ запросов), но **сетевой путь из РФ-сегмента к IP 5.129.207.254 был временно недоступен** ~5 минут.

## 4. MTR-trace от VPS → Yandex Moscow (2026-05-11 06:27 UTC)

Команда: `mtr --report --report-cycles 5 --tcp --port 443 87.250.250.242`

| Hop | IP | Loss% | Last (ms) | Avg (ms) | Best | Worst (ms) | StDev |
|---|---|---|---|---|---|---|---|
| 1 | 5.129.192.1 (Timeweb GW) | 0% | 0.7 | 0.6 | 0.4 | 0.9 | 0.2 |
| **2** | **212.164.50.113** | **0%** | **4119** | **824.8** | 1.0 | **4119** | **1841.9** |
| 3 | 185.140.148.157 | 0% | 42.6 | 42.9 | 42.6 | 43.2 | 0.2 |
| **4** | **94.25.47.122** | **0%** | 42.9 | **255.9** | 42.4 | **1108** | **476.7** |
| 5+ | * | 100% (ICMP filtered) | — | — | — | — | — |

**Critical:** hop 2 (`212.164.50.113` — выглядит как Timeweb edge / peering) показывает спорадические delays **до 4 секунд** при baseline 1ms. StDev 1841 ms говорит о sustained instability, не случайном blip. Hop 4 (`94.25.47.122` — upstream) показывает delays **до 1.1 секунды**. Это объясняет TIMEOUTs HTTP-запросов: curl timeout 5s, при upstream delay 4s — запрос едва успевает или fails.

## 5. Дополнительные observations

- За 1.5 суток непрерывного мониторинга RU vantage поймал **1 полный outage** (18:06) с длительностью ~5 минут.
- Internal health-check показывает шум (~40 локальных timeout'ов за тот же период), но большинство — артефакты cron-execution под swap pressure на VPS, не подтверждаются RU vantage.
- VPS постоянно атакуется внешними scan-ботами (~30 connection attempts/мин блокируются ufw); fail2ban забанил 29 IP за период. Это локальная нагрузка, но не должна затрагивать upstream peering.

## 6. Гипотезы

1. **🔴 Основная — Upstream peering instability** — hop 2 (212.164.50.113) показывает spikes до 4с регулярно. Это infrastructure issue на peering Timeweb с upstream или edge router нестабилен. **Это ваша сторона.**
2. **TSPU / РФ-провайдер фильтрация** — менее вероятно: MTR показывает packet delay, но не drop (loss% = 0).
3. **Internal Timeweb network event** — что-то на стороне инфраструктуры новосибирского DC.

## 7. Запрос

1. **Проверить нестабильность peering hop `212.164.50.113`** — что с ним? Edge router Timeweb или ближайший upstream?
2. **Проверить hop `94.25.47.122`** — second unstable hop.
3. **Проверить incidents** в внутренней системе мониторинга Timeweb для IP 5.129.207.254 / ноды `kvmnvm-841` за период 2026-05-10 17:50–18:20 UTC (20:50–21:20 МСК).
4. **Проверить блокировки РКН / TSPU** для IP 5.129.207.254 или диапазона.
5. **Возможна ли смена IP** на менее проблемный диапазон / migration на другую ноду, если фильтрация / peering issue подтвердятся?
6. **Если ничего из перечисленного** — provide диагностику с вашей стороны: что было в логах upstream BGP / firewall / monitoring в указанный временной интервал?

## 8. Конфигурация VPS (для справки)

- ОС: Ubuntu 24.04, kernel 6.8.0-106
- RAM: 2 GB (используется 1.3 GB + кэш, swap 2 GB используется 1.3 GB)
- Disk: 40 GB NVMe (68% used)
- CPU: 2 × 3.3 ГГц
- Сервисы: 6 PM2 + 16 Docker контейнеров + 8 systemd сервисов + nginx (6 vhosts) + Postgres 16
- Bandwidth: 100 Мбит/с (использование <3 Мбит/с)
- fail2ban active, ufw firewall enabled (закрытые порты 25/465/587/2525 как требует anti-spam policy Timeweb)

---

**Контакт:** готов предоставить дополнительные логи (mtr-traces в реальном времени из РФ-провайдера, journalctl за интересующий период, nginx access/error logs) по запросу.

**Public dashboard для мониторинга текущего состояния:** https://monitor.smm-ministr.ru/dashboard/
