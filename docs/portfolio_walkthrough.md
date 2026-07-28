# DeliveryPulse: portfolio walkthrough

## Проблема

DeliveryPulse исследует, почему синтетические логистические перевозки
опаздывают или становятся убыточными, и переводит результаты в проверяемые
управленческие pilots.

## Архитектура и запуск

Воспроизводимый генератор создаёт восемь связанных CSV. Независимый quality
gate проверяет схему, ключи, хронологию и бизнес-правила. Проверенные данные
загружаются в DuckDB, где SQL строит пять витрин с документированным зерном.
Python отвечает за оркестрацию, статистику, графики и отчёты.

Быстрый локальный путь:

```text
generate → quality → warehouse build/validate → eda
         → hypotheses → recommendations
```

PostgreSQL, Metabase, Compose и CI являются optional engineering-слоем; DuckDB
остаётся source of truth.

## Качество и витрины

Raw не исправляется на месте, а технический manifest не используется обычным
аналитическим кодом. SQL предотвращает размножение строк: events и maintenance
агрегируются до зерна до join. Деньги хранятся как DECIMAL/NUMERIC, штраф
уменьшает net revenue и не включается в delivery cost.

## EDA и гипотезы

EDA описывает маршруты, клиентов, события, прибыльность, priority и автопарк без
причинных формулировок. Protocol этапа 6 заранее зафиксировал H1–H6, controls,
effect sizes и диагностику. H2, H3 и H5 supported; H1 primary not_supported;
H4 и H6 inconclusive.

## Рекомендации

P1 — pilots express-процесса и breakdown response. P2 — коммерческий review
клиентов достаточного объёма и ограниченное измерение loading duration.
Maintenance требует дополнительных longitudinal data, а overload policy
остаётся HOLD. Сценарные суммы — иллюстрация, не прогноз.

## BI и engineering decisions

Publisher читает validated DuckDB read-only, загружает явные типы в staging
PostgreSQL schema, сверяет строки и метрики и выполняет atomic schema swap.
Metabase использует только publish marts. Compose не хранит секретов и не
монтирует домашние каталоги. CI проверяет малый end-to-end путь без full
generation и тяжёлых моделей.

## Ограничения

Все данные синтетические. Наблюдательные связи не устанавливают причинность.
Локальный Compose не заменяет production security, backup и HA. Реальные
решения требуют pilot на корпоративных данных, проверки качества, безопасности
и коммерческих рисков.
