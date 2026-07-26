"""Deterministic Markdown reporting for exploratory analysis."""

# Report prose and table specifications are intentionally kept as readable units.
# ruff: noqa: E501

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pandas as pd

from delivery_pulse.analysis.loader import AnalysisContext


def _value(value: object, *, percent: bool = False, money: bool = False) -> str:
    if pd.isna(value):
        return "—"
    number = float(cast(Any, value))
    if percent:
        return f"{number:.1%}"
    if money:
        return f"{number:,.0f} RUB".replace(",", " ")
    return f"{number:,.2f}".replace(",", " ")


def _table(frame: pd.DataFrame, columns: list[str], limit: int = 10) -> str:
    selected = frame.loc[:, columns].head(limit).copy()
    if selected.empty:
        return "_Нет наблюдений._"
    headers = [str(column) for column in selected.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in selected.itertuples(index=False, name=None):
        lines.append(
            "| "
            + " | ".join("—" if pd.isna(item) else str(item) for item in row)
            + " |"
        )
    return "\n".join(lines)


def hypothesis_candidates() -> list[dict[str, str]]:
    """Return the six pre-registered candidates for formal Stage 6 testing."""
    return [
        {
            "title": "Погрузочный простой связан с риском опоздания",
            "metric": "late_delivery_rate и delay_minutes",
            "groups": "доставки с loading_delay против доставок без него",
            "confounders": "маршрут, клиент, priority, месяц, тип транспорта",
            "minimum": "не менее 200 доставок и 30 опозданий в каждой группе",
            "method": "стратификация и многомерная модель бинарного/непрерывного исхода",
            "confirmed": "пересмотреть SLA погрузки и приоритеты обработки площадок",
            "not_confirmed": "не вводить общий норматив; искать локальные площадки и сегменты",
        },
        {
            "title": "Express имеет иной риск опоздания после контроля состава рейсов",
            "metric": "on_time_delivery_rate",
            "groups": "express против standard",
            "confounders": "маршрут, клиент, сезон, масса, транспорт, события",
            "minimum": "не менее 500 доставок каждого priority",
            "method": "разница долей со стратификацией и логистическая модель",
            "confirmed": "скорректировать обещанный SLA или операционный приоритет express",
            "not_confirmed": "сохранить единые процессы и не менять SLA по простому сравнению",
        },
        {
            "title": "Поломка связана с убыточностью сверх влияния маршрута",
            "metric": "delivery_profit и loss_making_delivery_rate",
            "groups": "доставки с breakdown против доставок без breakdown",
            "confounders": "маршрут, расстояние, возраст/тип ТС, priority, месяц",
            "minimum": "не менее 100 доставок с поломкой",
            "method": "стратифицированное сравнение и робастная модель прибыли",
            "confirmed": "приоритизировать профилактику на наиболее дорогих экспозициях",
            "not_confirmed": "оценивать ТО по надёжности и SLA, а не по марже рейса",
        },
        {
            "title": "Риск поломки различается по экспозиции и типу транспорта",
            "metric": "breakdowns_per_10k_km",
            "groups": "типы транспорта и группы возраста",
            "confounders": "пробег, часы рейса, маршрутный класс, календарный месяц",
            "minimum": "не менее 10 000 км экспозиции на сравниваемую группу",
            "method": "модель счётных событий с offset пробега и анализ чувствительности",
            "confirmed": "изменить интервалы ТО для подтверждённых групп риска",
            "not_confirmed": "оставить единый регламент и продолжить накопление экспозиции",
        },
        {
            "title": "Клиенты различаются по марже после контроля маршрутного микса",
            "metric": "group_margin_pct",
            "groups": "крупные клиенты и клиентские сегменты",
            "confounders": "маршрут, priority, сезон, масса, события",
            "minimum": "не менее 90 доставок на клиента или укрупнение до сегмента",
            "method": "иерархическая/многомерная модель прибыли и bootstrap интервалов",
            "confirmed": "пересмотреть тарифы или условия обслуживания целевых клиентов",
            "not_confirmed": "не менять договоры; корректировать маршрутный или продуктовый микс",
        },
        {
            "title": "Операционный перегруз связан с убыточностью только в сегментах",
            "metric": "loss_making_delivery_rate и delivery_profit",
            "groups": "допустимый operational overload против нормы",
            "confounders": "тип ТС, маршрут, масса, расстояние, priority",
            "minimum": "не менее 100 реальных перегрузов и 30 на ключевой сегмент",
            "method": "стратифицированный анализ взаимодействий без смешения с DQ-дефектами",
            "confirmed": "ограничить перегруз в выявленных сегментах",
            "not_confirmed": "не вводить общий запрет; сохранить действующий допустимый порог",
        },
    ]


def write_report(
    context: AnalysisContext,
    tables: dict[str, pd.DataFrame],
    figures: dict[str, Path],
    output_path: Path,
    *,
    min_group_size: int,
) -> Path:
    """Write an answer-first Markdown EDA report based on computed tables."""
    baseline: dict[str, Any] = context.baseline
    delivered_count = int(baseline["delivered_count"])
    late_count = round(delivered_count * (1 - float(baseline["on_time_delivery_rate"])))
    late_rate = late_count / delivered_count if delivered_count else None
    route_loss = tables["route_loss_ranking"]
    customer_loss = tables["customer_loss_ranking"]
    priorities = tables["priority"]
    overload = tables["profitability_segments"].query(
        "dimension == 'operational_overload'"
    )
    hypotheses = hypothesis_candidates()
    report = f"""# DeliveryPulse: разведочный анализ

## Техническое резюме

Анализ выполнен по проверенному DuckDB warehouse: профиль
`{context.metadata["profile"]}`, seed `{context.metadata["seed"]}`, период с
`{context.metadata["start_date"]}` на {context.metadata["months"]} месяцев.
Набор синтетический; результаты описывают сгенерированный сценарий и не являются
оценкой реальной компании или доказательством причинности.

## Ключевые показатели

- Заказы: {int(baseline["orders_count"])}; доставки: {int(baseline["deliveries_count"])}.
- Delivered / failed / cancelled: {int(baseline["delivered_count"])} /
  {int(baseline["failed_count"])} / {int(baseline["cancelled_count"])}.
- OTD: {_value(baseline["on_time_delivery_rate"], percent=True)}; медиана / p90
  опоздания среди опоздавших: {_value(baseline["median_delay_minutes"])} /
  {_value(baseline["p90_delay_minutes"])} минут.
- Опоздавших завершённых доставок: {late_count}
  ({_value(late_rate, percent=True)} от delivered).
- Чистая выручка: {_value(baseline["total_net_revenue"], money=True)};
  затраты: {_value(baseline["total_delivery_cost"], money=True)}; прибыль:
  {_value(baseline["total_delivery_profit"], money=True)}.
- Групповая маржа: {_value(baseline["group_margin_pct"], percent=True)};
  убыточных доставок: {_value(baseline["loss_making_delivery_rate"], percent=True)};
  сумма убытков: {_value(baseline["loss_amount"], money=True)}.
- Поломки: {int(baseline["breakdown_count"])}; операционные перегрузы:
  {int(baseline["operational_overload_count"])}; полнота финансов:
  {_value(baseline["data_completeness_rate"], percent=True)}.

## Метод и источники

KPI берутся из пяти SQL-витрин и baseline SQL. `route_events` используется
только для флага `route_deviation` и детализации затрат по типу события — не для
повторного расчёта KPI. Временные срезы используют Europe/Moscow. Групповая
маржа — `sum(profit) / sum(net_revenue)`, а не среднее построчных маржей.

## Временная динамика

**Факт:** доступны {len(tables["daily"])} дневных и
{len(tables["monthly"])} месячных наблюдений.

**Описательное наблюдение:** графики показывают совместную динамику объёма,
OTD, прибыли и групповой маржи. Совпадение изменений по времени не
интерпретируется как причинная связь.

## Маршруты

Размер выборки всегда показан рядом с процентами. Для рейтингов OTD и маржи
применён минимум {min_group_size} доставок.

{_table(route_loss, ["route_code", "deliveries_count", "loss_amount", "group_margin_pct", "on_time_delivery_rate"])}

**Описательное наблюдение:** наибольшая сумма убытков сосредоточена в верхних
строках таблицы, но это сочетает частоту рейсов и риск отдельной доставки.
**Возможное объяснение:** маршрутный класс, расстояние и события могут
одновременно влиять на SLA и экономику. Это требует контроля на этапе 6.

## Клиенты

Группы объёма определены заранее: малая — менее {min_group_size}, средняя —
от {min_group_size} до {min_group_size * 3 - 1}, крупная — не менее
{min_group_size * 3} доставок.

{_table(customer_loss, ["customer_name", "customer_segment", "deliveries_count", "volume_band", "loss_amount", "group_margin_pct"])}

**Факт:** клиентов с малой выборкой:
{int((tables["customers"]["volume_band"] == "small_sample").sum())}.
Их процентные рейтинги не считаются надёжными.

Крупные клиенты с наименьшей маржой:

{_table(tables["customer_large_low_margin"], ["customer_name", "deliveries_count", "group_margin_pct", "loss_amount"])}

Клиенты с наибольшей долей express:

{_table(tables["customer_high_express"], ["customer_name", "deliveries_count", "express_share", "group_margin_pct"])}

## События и задержки

{_table(tables["event_comparisons"], ["event_type", "comparison_group", "deliveries_count", "late_delivery_rate", "median_delay_minutes", "p90_delay_minutes", "profit_missing_rate"])}

**Описательное наблюдение:** различия «с событием / без события» являются
нескорректированными. **Возможное объяснение:** события чаще возникают на
сложных маршрутах, поэтому простая связь может исчезнуть после контроля.

## Убыточность

Выбросы не удалены. На гистограмме визуальный диапазон ограничен p1–p99, а
число значений за границами указано в подписи. Отдельные сегменты убыточности:

{_table(tables["profitability_segments"], ["dimension", "segment", "deliveries_count", "loss_making_deliveries", "loss_making_delivery_rate", "group_margin_pct"])}

## Автопарк

Нормированные поломки интерпретируются только вместе с пробегом и часами.
Автомобили с пробегом менее 10 000 км помечаются как недостаточно
экспонированные для индивидуального рейтинга.

{_table(tables["vehicle_breakdown_ranking"], ["vehicle_code", "vehicle_type", "actual_distance_km", "trip_hours", "breakdown_count", "breakdowns_per_10k_km"])}

Возрастные группы:

{_table(tables["vehicle_ages"], ["age_band", "vehicles_count", "actual_distance_km", "breakdown_count", "breakdowns_per_10k_km"])}

## Standard и express

{_table(priorities, ["priority", "deliveries_count", "on_time_delivery_rate", "median_delay_minutes", "p90_delay_minutes", "total_delivery_profit", "group_margin_pct", "loss_making_delivery_rate"])}

Это описательное сравнение без проверки значимости и без контроля различий
маршрутного и клиентского состава.

## Операционный перегруз

{_table(overload, ["segment", "deliveries_count", "loss_making_delivery_rate", "group_margin_pct"])}

Реальный допустимый перегруз не смешивается с искусственными DQ-дефектами:
анализ выполняется только на наборе, прошедшем quality и warehouse validation.

## Графики

"""
    report += "\n".join(
        f"- [{name}]({path.relative_to(output_path.parent).as_posix()})"
        for name, path in sorted(figures.items())
    )
    report += """

## Ограничения

- Данные синтетические и содержат заложенные, шумовые и сегментные эффекты.
- EDA не оценивает статистическую неопределённость и не доказывает причинность.
- Наблюдения с малой выборкой и малой экспозицией не подходят для рейтинга.
- Точечная детализация событий не заменяет канонические SQL-метрики.
- Raw CSV и DuckDB не изменяются; автоматическое исправление не выполняется.

## Кандидаты для этапа 6

"""
    for index, item in enumerate(hypotheses, start=1):
        report += f"""### {index}. {item["title"]}

- Целевая метрика: {item["metric"]}.
- Группы: {item["groups"]}.
- Возможные смешивающие факторы: {item["confounders"]}.
- Минимальная выборка: {item["minimum"]}.
- Рекомендуемый метод: {item["method"]}.
- При подтверждении: {item["confirmed"]}.
- При неподтверждении: {item["not_confirmed"]}.

"""
    report += """## Следующий шаг

На этапе 6 заранее зафиксировать выборки, методы и критерии решений для 4–6
кандидатов, затем выполнить формальные проверки без подгонки генератора.
"""
    target = output_path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report, encoding="utf-8")
    return target
