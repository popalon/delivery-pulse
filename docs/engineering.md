# Optional engineering-контур DeliveryPulse

## Архитектура

DuckDB остаётся источником истины первого релиза. PostgreSQL — только
дополнительный publish-слой для BI:

```text
raw CSV → quality gate → DuckDB source tables → SQL marts
                                           ↓ read-only
                           PostgreSQL staging schema
                                           ↓ validation
                              atomic target-schema swap
                                           ↓
                                        Metabase
```

Публикуются `customers`, `routes`, `vehicles`, пять витрин,
`warehouse_metadata` и `publish_metadata`. Raw CSV, quality manifest,
коэффициенты моделей, секреты и локальные пути не публикуются.

## Безопасность и конфигурация

PostgreSQL support устанавливается отдельно:

```bash
python -m pip install -e ".[dev,postgres]"
```

CLI-значения имеют приоритет над environment. Пароль нельзя передать открытым
аргументом: `--password-env` задаёт имя переменной, по умолчанию
`POSTGRES_PASSWORD`. Он исключён из `repr` и логов. `.env.example` содержит
только шаблон; `.env` игнорируется.

## Транзакционная публикация

```bash
python -m delivery_pulse publish postgres \
  --database data/processed/delivery_pulse.duckdb \
  --host localhost --port 5432 \
  --dbname delivery_pulse --user delivery_pulse \
  --schema delivery_pulse --mode create
```

Windows PowerShell:

```powershell
$env:POSTGRES_PASSWORD = "local-only-password"
python -m delivery_pulse publish postgres `
  --database data/processed/delivery_pulse.duckdb `
  --host localhost --port 5432 `
  --dbname delivery_pulse --user delivery_pulse `
  --schema delivery_pulse --mode create
```

`create` завершается ошибкой при существующей target schema. `replace` требует
одновременно `--mode replace --force`. Pipeline:

1. валидирует DuckDB и открывает его read-only;
2. создаёт отдельную staging schema;
3. создаёт таблицы с явными PostgreSQL-типами;
4. загружает Decimal/NULL без pandas-float преобразования;
5. сверяет строки, зерно, денежные суммы, статусы, OTD и loss count;
6. атомарно переименовывает schema внутри транзакции;
7. при исключении выполняет rollback.

`--validate-only` не изменяет PostgreSQL. Исходный SHA-256 DuckDB проверяется
после публикации.

## Docker Compose

`compose.yaml` поднимает PostgreSQL 16 и Metabase 0.50 в отдельной сети с
именованными volumes. PostgreSQL имеет healthcheck. Privileged mode и
монтирование домашнего каталога отсутствуют.

```bash
cp .env.example .env
docker compose config
docker compose up -d
docker compose ps
```

PowerShell:

```powershell
Copy-Item .env.example .env
docker compose config
docker compose up -d
docker compose ps
```

Перед запуском замените example password. Команда `docker compose down -v`
удаляет данные volumes и не должна выполняться без явного решения пользователя.

## Doctor и CI

`python -m delivery_pulse doctor` проверяет Python, импорты, каталоги, DuckDB,
Docker и Compose без изменения системы. PostgreSQL проверяется только с
`--check-postgres`.

GitHub Actions запускает Python 3.11, pytest, Ruff, mypy, whitespace check и
малый end-to-end smoke. Full generation, тяжёлые модели, Metabase и внешняя
публикация в CI не запускаются.

Integration-тесты PostgreSQL opt-in и автоматически пропускаются без
`DELIVERY_PULSE_TEST_POSTGRES`. Локальный Compose-контур не является
production deployment: отсутствуют TLS, backup, HA, SSO и orchestration.
