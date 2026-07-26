# DuckDB и SQL-слой DeliveryPulse

## Назначение

Локальный warehouse загружает восемь проверенных raw CSV в DuckDB и строит пять
аналитических витрин. Python управляет путями, quality gate, транзакцией,
загрузкой и validation. Бизнес-формулы находятся в версионированных SQL-файлах.

Raw CSV открываются только для чтения. `quality_issues_manifest.csv` не
загружается, не создаёт таблицу и не влияет на расчёты.

## Версии и ограничения

- Python 3.11+;
- DuckDB `>=1.2,<2`;
- единственная валюта — RUB;
- исходные `TIMESTAMP` хранят UTC без смещения;
- календарные даты и месяцы получаются после перевода из UTC в
  `Europe/Moscow`;
- warehouse рассчитан на локальный однопроцессный аналитический сценарий, а не
  на параллельную production-загрузку.

## Сборка и отказоустойчивость

Порядок:

1. quality pipeline проверяет raw-набор;
2. `failed` останавливает сборку, `passed_with_warnings` допускается с явным
   сообщением;
3. читаются только восемь ожидаемых CSV и `metadata.json`;
4. DDL создаёт таблицы с явными типами;
5. CSV загружаются по общей карте `DUCKDB_COLUMN_TYPES`;
6. фактические строки сверяются с metadata;
7. SQL-файлы витрин выполняются в числовом порядке;
8. создаётся `warehouse_metadata`;
9. validation проверяет объекты, зерно, строки и формулы;
10. только после успешного commit временная база атомарно заменяет целевую.

Без `--force` существующая база сохраняется. При ошибке временная база и WAL
удаляются, поэтому частично построенный warehouse не публикуется.

## Source tables

`customers`, `routes`, `drivers`, `vehicles`, `orders`, `deliveries`,
`route_events`, `maintenance` сохраняют исходное зерно и типы из
`docs/data_model.md`. Идентификаторы — `BIGINT`, деньги — `DECIMAL(14,2)`,
календарные даты — `DATE`, время — `TIMESTAMP`, флаги — `BOOLEAN`.

`warehouse_metadata` содержит версию проекта и схемы, версию генератора, seed,
профиль, период, время загрузки, диагностический source path и JSON со строками
source tables. `source_directory` не используется аналитическими запросами.

## Lineage и зерно витрин

```text
orders ─┬─ deliveries ─┬─ route_events
routes ─┤               └─ delivery_performance_mart
vehicles┘                      │
                               ├─ route_daily_mart
orders + deliveries + events ─ delivery_financial_mart
                               └─ customer_monthly_mart

delivery_performance_mart + maintenance
    └─ vehicle_reliability_mart
```

### `delivery_performance_mart`

Зерно: одна строка на `delivery_id`.

`route_events` сначала сворачиваются до доставки. Отсутствие событий даёт
нулевые counts и event minutes. SLA, cycle time, delay и `is_on_time`
рассчитываются только для `delivered`; неприменимые значения остаются NULL.
Failed и cancelled не исключаются.

### `delivery_financial_mart`

Зерно: одна строка на `delivery_id`.

События сначала агрегируются до доставки. Известное отсутствие событий даёт
`event_extra_cost = 0`. При неизвестном обязательном компоненте
`financial_data_complete = false`, а полная стоимость, прибыль и маржа — NULL.

```text
net_revenue = quoted_revenue - penalty_amount
total_delivery_cost = fuel + driver + toll + maintenance + other + event
delivery_profit = net_revenue - total_delivery_cost
margin_pct = delivery_profit / nullif(net_revenue, 0)
```

Штраф не входит в `total_delivery_cost`.

### `route_daily_mart`

Зерно: `route_id × calendar_date`. Используется дата планового выезда после
перевода UTC → `Europe/Moscow`.

Считает объём, статусы, SLA, задержку по опоздавшим, экономику, убытки,
поломки и погрузочные простои. Групповая маржа — отношение сумм:

```text
sum(delivery_profit) / nullif(sum(net_revenue), 0)
```

Построчные проценты не усредняются.

### `customer_monthly_mart`

Зерно: `customer_id × calendar_month`. Месяц определяется по requested pickup
в бизнес-часовом поясе. Основа — `orders` с LEFT JOIN доставки, поэтому
сохраняются ещё не назначенные заказы. Рядом с долями публикуются counts.

### `vehicle_reliability_mart`

Зерно: `vehicle_id × calendar_month`.

Доставки и обслуживание независимо агрегируются до vehicle-month, затем
соединяются. В экспозицию километров и часов входят только завершённые рейсы с
положительными значениями. Деление на ноль возвращает NULL.

```text
breakdowns_per_10k_km = breakdown_count / actual_distance_km * 10000
breakdowns_per_1000_trip_hours = breakdown_count / trip_hours * 1000
```

## Baseline

`sql/analysis/001_baseline_metrics.sql` использует только созданные витрины.
Он возвращает объём, статусы, SLA, задержку, финансы, убытки, поломки,
операционные перегрузы до 5% и полноту финансовых данных.

## Защита от размножения строк

- события группируются до `delivery_id` до соединения с доставкой;
- обслуживание группируется до `vehicle_id × month`;
- delivery marts валидируются против числа уникальных доставок;
- event costs сверяются с суммой source-событий;
- сумма maintenance events сверяется с source;
- route/customer/vehicle marts проверяются на уникальность зерна.

## CLI: Linux

```bash
python -m delivery_pulse warehouse build \
  --input-dir data/raw \
  --database data/processed/delivery_pulse.duckdb

python -m delivery_pulse warehouse validate \
  --database data/processed/delivery_pulse.duckdb

python -m delivery_pulse warehouse info \
  --database data/processed/delivery_pulse.duckdb

python -m delivery_pulse warehouse baseline \
  --database data/processed/delivery_pulse.duckdb
```

## CLI: Windows PowerShell

```powershell
python -m delivery_pulse warehouse build `
  --input-dir data/raw `
  --database data/processed/delivery_pulse.duckdb

python -m delivery_pulse warehouse validate `
  --database data/processed/delivery_pulse.duckdb

python -m delivery_pulse warehouse info `
  --database data/processed/delivery_pulse.duckdb

python -m delivery_pulse warehouse baseline `
  --database data/processed/delivery_pulse.duckdb
```

Коды: 0 — успех, 1 — failed quality/validation, 2 — параметры, файлы или
исполнение. `--skip-quality-check` предназначен только для диагностических
сценариев. Он не отключает проверку metadata и warehouse validation.
