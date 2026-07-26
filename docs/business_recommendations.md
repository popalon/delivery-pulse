# DeliveryPulse: бизнес-рекомендации

## Метод и границы

Рекомендации построены по заранее закреплённой
[методологии](recommendation_methodology.md) из результатов
[EDA](eda_findings.md) и [формальной проверки](hypothesis_results.md). Данные
синтетические, дизайн наблюдательный. Ни одна связь ниже не названа причинной,
а сценарии являются иллюстрацией механики решения, не финансовым прогнозом.

## Приоритетная матрица

| ID | Evidence | Priority | Action |
|---|---|---|---|
| R1 Express | `strong_observational_evidence` | P1 | `pilot` |
| R2 Поломки | `strong_observational_evidence` | P1 | `pilot` |
| R3 Клиенты | `strong_observational_evidence` | P2 | `pilot` |
| R4 Погрузка | `moderate_or_secondary_evidence` | P2 | `pilot` |
| R5 ТО | `insufficient_evidence` | P3 | `collect_more_data` |
| R6 Перегруз | `insufficient_evidence` | HOLD | `do_not_act_yet` |

P1 означает начало подготовки ограниченного pilot, а не масштабное внедрение.
Все первоначальные решения остаются `proposed`, `monitoring` или
`blocked_by_evidence`.

## Карточки R1–R6

### R1. Express-операции

- Факт: H2 supported; adjusted risk difference опоздания +6,22 п.п.
- Интерпретация: связь сохраняется после контроля состава рейсов, но причинность
  priority не установлена.
- Действие: pilot SLA, раннего назначения ресурсов, маршрутного буфера и
  риск-тарификации на ограниченном числе маршрутов.
- KPI: express OTD, late count, p90 delay, penalty amount, group margin.
- Guardrails: standard OTD, failed rate, безопасность.

### R2. Управление поломками

- Факт: H3 supported; adjusted loss-risk difference +83,69 п.п.; разница прибыли
  −69 870 RUB, p1–p99 sensitivity −53 082 RUB.
- Интерпретация: тяжёлые убытки концентрируются при breakdown; экстремальный OR
  нельзя трактовать как точный причинный множитель.
- Действие: pilot резервного автомобиля, SLA реакции, эвакуации, замены
  транспорта, маршрутизации риска и контроля event cost.
- KPI: breakdown loss rate, средний убыток, downtime, recovery time,
  breakdowns per 10k km, доступность парка.
- Ограничение: H4 не поддерживает изменение интервалов планового ТО.

### R3. Клиентская прибыльность

- Факт: H5 supported; 165 клиентов прошли порог 90 доставок, диапазон
  скорректированных fixed effects — 23 963 RUB.
- Действие: pilot-review тарифов, SLA, штрафов, route mix, express share и
  минимальной цены только для клиентов достаточного объёма.
- KPI: adjusted profit, group margin, loss amount, retention, orders count.
- Ограничение: нескорректированная маржа и малая выборка недостаточны.

### R4. Длительность погрузки

H1 primary `not_supported`: бинарный loading delay не является основанием для
масштабной программы. Secondary duration signal позволяет только измерение
длительности, alerts длинных простоев и ограниченный pilot.

### R5. Исследование обслуживания

H4 `inconclusive`. Интервалы ТО не менять. Следует повысить полноту pre-trip
condition, дней и километров после ТО, отделить scheduled maintenance от repair
и накопить минимум ещё 12 месяцев.

### R6. Операционный перегруз

H6 `inconclusive`: 206 перегрузов и шесть убытков не дают достаточных ячеек.
Ограничения безопасности сохраняются; финансовый вывод делать нельзя.

## Сценарии и pilots

Для R1–R3 pipeline создаёт `conservative`, `base` и `optimistic`.
Редактируются baseline cases, coverage, assumed reduction, средняя ценность
случая, program cost и evaluation period. Снижение не выводится из odds ratio.
Результат маркируется `illustrative_scenario_not_forecast`.

Для P1/P2 задаются сравнительная группа, 8–12-недельный или договорный период,
минимальная выборка, KPI, guardrail, success/stop criteria, бизнес-роль и риски.
Конкретные люди или календарные даты не назначаются.

## План 30/60/90

- 0–30: измерения, выбор групп, baseline, KPI и guardrails.
- 31–60: ограниченные pilots и еженедельный quality review; без расширения при
  ухудшении guardrails.
- 61–90: решение `scale`, `modify` или `stop`, повторная проверка и обновление
  decision register.

Финансовый результат заранее не обещается. Решения требуют pilot на реальных
данных с операционной, финансовой и safety-проверкой.
