# Тикет в Timeweb support — VPS 5.129.207.254 нестабильность сетевого доступа

**Готово к отправке через ticket-систему ЛК Timeweb после Maxim review.**

---

## Тема (subject)

Эпизодическая недоступность VPS 5.129.207.254 (тариф Cloud NSK 40) с конкретными timestamps и cross-vantage логами

## Тело тикета

Здравствуйте.

Наблюдаю эпизодическую сетевую недоступность VPS 5.129.207.254 (тариф Cloud NSK 40, hostname `nsk-1-vm-nz9b`, нода `kvmnvm-841`).

### Симптомы

С разных устройств в РФ-сети (МТС, Билайн, Wi-Fi разных провайдеров) периодически наблюдаются:
- TLS handshake timeout для всех HTTPS-сайтов на VPS (`zavod.smm-ministr.ru`, `survey.smm-ministr.ru`, `brand.smm-ministr.ru`, `krutly.com`)
- `kex_exchange_identification: read: Connection reset by peer` при SSH-подключениях
- Восстановление само через несколько минут
- Помогает обход через VPN другой страны → подозрение на сетевую фильтрацию на RU-стороне

### Развёрнутый мониторинг для воспроизведения

Чтобы зафиксировать события timestamp'ами, развёрнут multi-vantage monitoring:

1. **VPS-internal** — health-check cron каждые 2 мин (`/var/log/pleyada-health.log`), измеряет локальные nginx-ответы
2. **External US/EU vantage** — GitHub Actions cron каждые 5 мин (Microsoft Azure DC, US Virginia / EU Ireland), HTTP/TCP probes из вне-РФ сети. Логи: https://github.com/lukonin33/vps-monitor/blob/main/logs/probes.csv
3. **External RU vantage** — Yandex Cloud Function (ru-central1, новосибирский DC) каждые 5 мин, HTTP/TCP probes из РФ-сегмента. Логи: https://github.com/lukonin33/vps-monitor/blob/main/logs/probes-ru.csv
4. **Dashboard** — https://monitor.smm-ministr.ru/dashboard/ (визуализация)

### Конкретный incident с cross-vantage evidence

**2026-05-10 18:06:14 UTC** (21:06 МСК):

| Vantage | Время (UTC) | Состояние |
|---|---|---|
| RU (Yandex Cloud, ru-central1) | **18:06:14** | **TIMEOUT для всех 4 HTTPS-сайтов + TCP-проверка порт 22 = FAIL + TCP-проверка порт 443 = FAIL** |
| RU (same vantage) | 18:01:13 | Все 4 сайта OK + TCP 22 OK + TCP 443 OK |
| RU (same vantage) | 18:11:11 | Восстановление: все 4 сайта OK + TCP OK |
| US/EU (GitHub Actions) | **18:09:04** (3 минуты после RU FAIL) | **Все 4 сайта OK + TCP 22 OK + TCP 443 OK** |

**Интерпретация:** в момент когда RU vantage не мог установить TCP-соединение к 5.129.207.254 на порты 22 и 443 — US/EU vantage всего через 3 минуты в том же временном окне видел VPS полностью доступным. Это означает что **сам VPS не падал** (физически работал, обслуживал запросы из не-РФ сети), но **сетевой путь из РФ-сегмента к IP 5.129.207.254 был временно недоступен** на ~5 минут.

### Хронология (внутренний `pleyada-health.log` за период)

Дополнительно VPS-internal health-check показал многочисленные локальные timeout'ы (~40 раз за 1.5 суток), но большая часть из них **не подтверждается RU vantage** — это, вероятно, артефакты cron-execution под нагрузкой swap (RAM 2 GB при 16 Docker контейнерах + 6 PM2 + 8 systemd сервисах = swap usage 1.3 GB / 2 GB постоянно). Только 18:06 — реально подтверждённый network event.

### Гипотезы (со стороны клиента)

1. **TSPU / РФ-провайдер фильтрация** — IP 5.129.207.254 (или диапазон Timeweb) попадает в временные блокировки RU-сегмента
2. **Upstream peering blip Timeweb с РФ-провайдерами** — кратковременная потеря peer с MTS / Ростелеком
3. **Internal Timeweb network event** — что-то на стороне инфраструктуры новосибирского DC

### Просьба

1. **Проверить** существуют ли incidents в внутренней системе мониторинга Timeweb для IP 5.129.207.254 / ноды `kvmnvm-841` за период 2026-05-10 17:50–18:20 UTC (20:50–21:20 МСК).
2. **Проверить** не попадает ли IP 5.129.207.254 или диапазон в блокировки РКН / TSPU (по реестрам / API).
3. **Возможна ли** смена IP на менее проблемный диапазон, если фильтрация подтвердится?
4. **Если ничего из перечисленного** — provide диагностику с вашей стороны: что было в логах upstream BGP / firewall / monitoring в указанный временной интервал?

### Контакт

Готов предоставить дополнительные логи / mtr-traces / повторно воспроизвести по запросу. Мониторинг продолжается, при появлении новых incidents — пришлю timestamps оперативно.

---

## Что приложить к тикету

1. **Скриншот RU vantage CSV** в окне 17:50–18:20 UTC ([прямая ссылка](https://github.com/lukonin33/vps-monitor/blob/main/logs/probes-ru.csv) → найти строки 2026-05-10T18:*)
2. **Скриншот GA vantage CSV** в окне 18:00–18:30 UTC ([прямая ссылка](https://github.com/lukonin33/vps-monitor/blob/main/logs/probes.csv))
3. **Скриншот dashboard** в момент когда есть в матрице красная клетка (https://monitor.smm-ministr.ru/dashboard/)

## После отправки тикета

Если Timeweb отвечает «не воспроизводится» — escalate с приведением **дополнительных** incidents которые накопятся за неделю наблюдения. Триангуляция = neutral arbitrator: 3 независимых vantage не лгут.

Если Timeweb признаёт фильтрацию / network event — request смену IP или migration на другую ноду.

Если в течение 7 дней incidents не повторяются — closure thread с acknowledged "monitoring continues, please action if pattern emerges".
