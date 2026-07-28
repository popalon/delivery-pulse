# Metabase для DeliveryPulse

## Локальный запуск

1. Скопируйте `.env.example` в `.env` и замените example password.
2. Запустите `docker compose up -d`.
3. Дождитесь healthy PostgreSQL через `docker compose ps`.
4. Опубликуйте проверенный DuckDB командой из
   [engineering.md](engineering.md).
5. Откройте `http://localhost:3000` или порт `METABASE_PORT`.

При первом входе создаётся только локальный администратор Metabase. Добавьте
PostgreSQL database с host `postgres`, внутренним port `5432`, значениями
`POSTGRES_DB`/`POSTGRES_USER` и выбранным локальным паролем. Ограничьте
доступную schema значением `POSTGRES_SCHEMA`, затем запустите Sync database
schema и Re-scan field values.

## Назначение витрин

- `delivery_performance_mart`: SLA, задержки, события и экспозиция доставки;
- `delivery_financial_mart`: net revenue, затраты, прибыль и loss flag;
- `route_daily_mart`: маршрут × локальная дата;
- `customer_monthly_mart`: клиент × месяц;
- `vehicle_reliability_mart`: автомобиль × месяц.

Готовые карточки находятся в `sql/dashboard/`:

1. executive overview;
2. delivery reliability;
3. profitability;
4. fleet reliability;
5. monitoring KPI и guardrails R1–R6.

Запросы обращаются только к publish tables, а не к raw CSV.

## Правила метрик

Групповая маржа рассчитывается как
`SUM(delivery_profit) / NULLIF(SUM(net_revenue), 0)`. Нельзя усреднять
построчный `margin_pct`. Рядом с OTD, loss rate и другими процентами всегда
показывается `deliveries_count` или другая экспозиция. NULL означает
неизвестность, а не нулевое значение.

После `replace` выполните metadata sync. `publish_metadata` показывает версию,
SHA-256 источника и row counts, но не является бизнес-витриной.

Данные синтетические, результаты наблюдательные, а recommendation scenarios не
являются прогнозом. Фиктивные скриншоты или вывод о production-готовности не
используются.
