# DeliveryPulse

DeliveryPulse — портфолио-проект по аналитике данных для вымышленной
логистической компании. Цель проекта — определить, почему доставки опаздывают
или становятся убыточными, найти маршруты, клиентов и процессы с наибольшими
потерями и сформулировать проверяемые рекомендации.

> Статус: реализованы Python-каркас, генератор, контроль качества и локальный
> DuckDB warehouse с пятью SQL-витринами. EDA и проверка гипотез ещё не начаты.

## Что продемонстрирует проект

- Python, pandas и NumPy;
- SQL и DuckDB;
- Jupyter Notebook;
- проверку качества данных;
- проектирование аналитических витрин;
- проверку бизнес-гипотез;
- визуализацию и бизнес-интерпретацию;
- автоматические тесты, Git и документацию.

PostgreSQL, Metabase, Docker Compose и GitHub Actions отложены на будущие этапы.

## Аналитическая идея

Модель разделяет:

- маршрут — нормативное направление с расстоянием и временем в пути;
- заказ — коммерческое обязательство перед клиентом;
- доставку — конкретное исполнение заказа;
- события маршрута — операционные причины отклонений;
- техническое обслуживание — состояние автопарка;
- выручку и затраты — экономику отдельной доставки.

Основные результаты будущего анализа: on-time delivery rate, длительность и
величина опоздания, прибыль и маржа, стоимость километра, простои и надёжность
автомобилей, включая поломки на 10 000 км и 1 000 часов рейсов.

Контракты первого релиза: все суммы выражены в RUB; временные метки хранятся в
UTC, а бизнес-календарь и отображение используют `Europe/Moscow`. `NULL` в
финансовых данных означает неизвестное значение, а `0` — известное отсутствие
затрат.

## Документация

- [Техническое задание](PROJECT.md)
- [Roadmap](ROADMAP.md)
- [Модель данных](docs/data_model.md)
- [Метрики](docs/metrics.md)
- [Гипотезы](docs/hypotheses.md)
- [Сценарии генерации](docs/generation_scenarios.md)
- [Правила контроля качества](docs/data_quality_rules.md)
- [DuckDB и SQL-слой](docs/warehouse.md)
- [Правила работы в репозитории](AGENTS.md)

## Планируемая структура

```text
data/       локальные raw-, processed-данные и витрины
docs/       модель, метрики и гипотезы
notebooks/  последовательный аналитический рассказ
reports/    воспроизводимые изображения и итоговые материалы
sql/        DDL, витрины и аналитические запросы
src/        переиспользуемый Python-код
tests/      тесты данных, метрик и витрин
```

Полная структура описана в [PROJECT.md](PROJECT.md).

## Установка на Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Установка на Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Проверки качества

После активации виртуального окружения команды одинаковы на Linux и Windows:

```text
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy src
```

## CLI

Показать сведения о проекте и доступности рабочих каталогов:

```text
python -m delivery_pulse info
```

Безопасно создать отсутствующие локальные каталоги:

```text
python -m delivery_pulse init
```

`init` не удаляет и не перезаписывает существующие файлы. Основной Python-код
не требует Bash и использует `pathlib.Path`.

## Генерация данных

Профили: `test` для автотестов, `demo` для ручной проверки и `full` для
основного набора из 50 000 заказов.

Linux:

```bash
python -m delivery_pulse generate \
  --profile demo \
  --seed 42
```

Windows PowerShell:

```powershell
python -m delivery_pulse generate `
  --profile demo `
  --seed 42
```

Доступные параметры:

```text
--orders N
--seed N
--start-date YYYY-MM-DD
--months N
--output-dir PATH
--profile {test,demo,full}
--inject-quality-issues
--force
```

По умолчанию CSV записываются в `data/raw`, а `metadata.json` — в
`data/metadata`. Для пользовательского `--output-dir .../raw` metadata
сохраняется в соседнем каталоге `.../metadata`. Команда без `--force` не
перезаписывает существующие файлы.

## Данные и воспроизводимость

Генератор управляется явным seed и не использует глобальное случайное состояние.
Сгенерированные датасеты и локальные базы исключены из Git; пользователь сможет
воспроизвести их локально. Проект не должен содержать секреты или настоящие
данные компаний. Операционные перегрузы анализируются как бизнес-события, а
намеренные дефекты качества фиксируются в отдельном техническом manifest,
доступном тестам, но не аналитическому коду.

Обязательная глубокая проверка выполняется для шести приоритетных гипотез.
Остальные гипотезы дополнительные; генератор не обязан подтверждать их все.

## Контроль качества данных

Сначала создайте demo-набор, затем запустите независимую проверку. Raw CSV
открываются только для чтения и никогда не исправляются на месте.

Linux:

```bash
python -m delivery_pulse generate \
  --profile demo \
  --seed 42 \
  --output-dir data/raw

python -m delivery_pulse quality \
  --input-dir data/raw \
  --output-dir reports/quality
```

Windows PowerShell:

```powershell
python -m delivery_pulse generate `
  --profile demo `
  --seed 42 `
  --output-dir data/raw

python -m delivery_pulse quality `
  --input-dir data/raw `
  --output-dir reports/quality
```

Quality CLI поддерживает `--format {csv,json}`, `--fail-on
{critical,error,warning}` и `--max-samples N`. Код 0 означает пригодный набор
(возможно, с неблокирующими предупреждениями), код 1 — обнаруженные
блокирующие проблемы, код 2 — ошибку запуска или параметров. Создаются JSON
summary, CSV проблем, Markdown-отчёт и профиль таблиц.

Для проверки ноутбука установите отдельный минимальный extra:

Linux:

```bash
python -m pip install -e ".[dev,notebook]"
```

## DuckDB warehouse

Сборка запускает quality gate, загружает только восемь ожидаемых CSV и
атомарно публикует базу после validation. Raw CSV не изменяются, технический
manifest в базу не загружается.

Linux:

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

Windows PowerShell:

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

Без `--force` существующая база не перезаписывается. `passed_with_warnings`
разрешает сборку с явным предупреждением, а `failed` возвращает код 1 и не
создаёт базу. Подробные зерно, lineage и NULL-правила описаны в
[`docs/warehouse.md`](docs/warehouse.md).

Windows PowerShell:

```powershell
python -m pip install -e ".[dev,notebook]"
```

## Текущий следующий шаг

Этап DuckDB и SQL-слоя завершён. Следующий этап — EDA и визуализация; он
начинается только по отдельному разрешению.
