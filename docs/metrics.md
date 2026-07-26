# Бизнес-метрики DeliveryPulse

## Правила расчёта

- Если не указано иное, базовая выборка — доставки со статусом `delivered`.
- SLA сравнивается с `orders.promised_delivery_at`.
- Времена хранятся в UTC; календарные срезы и отображение первого релиза
  используют бизнес-зону `Europe/Moscow`.
- Проценты отображаются как `100 × доля`.
- Агрегированная маржа считается как отношение сумм, а не среднее процентов.
- Единственная валюта первого релиза — RUB.
- `NULL` в финансовом поле означает неизвестное значение, `0` — известное
  отсутствие соответствующих затрат. Неизвестное нельзя заменять нулём.
- Результат всегда сопровождается периодом, зерном и размером выборки.

## KPI-структура

Основные результаты:

1. `on_time_delivery_rate` — качество исполнения SLA;
2. `total_delivery_profit` и `margin_pct` — экономика доставок;
3. `loss_amount` — денежный масштаб убыточных перевозок.

Диагностические метрики: опоздание, длительность цикла, стоимость километра,
использование грузоподъёмности, события маршрута и надёжность автопарка.

Защитные метрики: доля неуспешных доставок и полнота ключевых данных, чтобы
улучшение скорости или маржи не скрывало ухудшение качества.

## 1. On-time delivery rate

Бизнес-смысл: доля завершённых доставок, выполненных не позже обещанного срока.

Зерно расчёта: доставка.

```text
is_on_time = actual_delivery_at <= promised_delivery_at
on_time_delivery_rate = count(is_on_time = true) / count(delivered)
```

Источники: `deliveries.actual_delivery_at`, `deliveries.delivery_status`,
`orders.promised_delivery_at`.

Исключения: отменённые, неуспешные и незавершённые доставки. Они показываются
отдельно в `failed_delivery_rate`.

Ограничение: метрика не показывает величину опоздания.

## 2. Late delivery rate

Доля завершённых доставок, завершённых после обещанного срока.

```text
late_delivery_rate = count(actual_delivery_at > promised_delivery_at)
                     / count(delivered)
```

При полной и непротиворечивой выборке равна `1 - on_time_delivery_rate`.

## 3. Delay minutes

Величина опоздания отдельной доставки:

```text
delay_minutes = greatest(
    0,
    date_diff('minute', promised_delivery_at, actual_delivery_at)
)
```

Агрегации: медиана и p90 по опоздавшим доставкам; среднее используется только
как дополнительное из-за чувствительности к выбросам.

## 4. Departure delay minutes

Отклонение фактического выезда от плана:

```text
departure_delay_minutes =
    date_diff('minute', planned_departure_at, actual_departure_at)
```

Отрицательное значение означает ранний выезд. Для метрики задержки выезда можно
применять `greatest(0, ...)`, но исходное отклонение сохраняется в витрине.

## 5. Delivery cycle time

Фактическое время от выезда до вручения:

```text
delivery_cycle_hours =
    date_diff('minute', actual_departure_at, actual_delivery_at) / 60
```

Используется медиана и p90 по сопоставимым маршрутам.

## 6. Total delivery cost

Прямые затраты на доставку:

```text
total_delivery_cost =
    fuel_cost
  + driver_cost
  + toll_cost
  + maintenance_allocated_cost
  + other_cost
  + route_event_extra_cost
```

Зерно: доставка. Перед объединением события сначала агрегируются до доставки,
чтобы не размножить строки.

`route_event_extra_cost` — агрегат событий; известное отсутствие событий даёт
`0`. Если любой обязательный компонент неизвестен, полная стоимость равна
`NULL`. `penalty_amount` не включается в затраты: он уменьшает выручку.

## 7. Net revenue

Выручка после штрафов и скидок за нарушение SLA:

```text
net_revenue = quoted_revenue - penalty_amount
```

В первом релизе предполагается, что заказ имеет одну доставку. При появлении
повторных попыток правило распределения выручки нужно пересмотреть.

## 8. Delivery profit

Управленческая прибыль отдельной доставки:

```text
delivery_profit = net_revenue - total_delivery_cost
```

Это contribution profit, а не бухгалтерская чистая прибыль: общие накладные
расходы не включены, если не распределены явно.

## 9. Margin

```text
margin_pct = delivery_profit / nullif(net_revenue, 0)
```

Для группы:

```text
group_margin_pct = sum(delivery_profit) / nullif(sum(net_revenue), 0)
```

Нельзя усреднять `margin_pct` по строкам. Нулевая или отрицательная чистая
выручка анализируется отдельно.

## 10. Loss-making delivery rate

```text
loss_making_delivery_rate =
    count(delivery_profit < 0) / count(deliveries with complete financial data)
```

Выборка требует полноты `quoted_revenue`, `penalty_amount`, `fuel_cost`,
`driver_cost`, `toll_cost`, `maintenance_allocated_cost`, `other_cost` и
агрегированного `route_events.extra_cost`. Если хотя бы одно значение неизвестно,
полная маржа не рассчитывается.

## 11. Loss amount

Абсолютная сумма отрицательной прибыли:

```text
loss_amount = sum(greatest(-delivery_profit, 0))
```

Метрика позволяет ранжировать маршруты и клиентов по денежному вкладу в потери,
а не только по доле убыточных рейсов.

## 12. Cost per actual kilometer

```text
cost_per_actual_km =
    total_delivery_cost / nullif(distance_actual_km, 0)
```

Сравнивать следует внутри сопоставимых типов транспорта и маршрутов.

## 13. Capacity utilization

```text
capacity_utilization =
    orders.cargo_weight_kg / vehicles.capacity_kg
```

Значение больше 1 при корректных исходных полях является реальным операционным
перегрузом. Искусственные дефекты выявляются проверками качества и техническим
manifest, который аналитический код не читает. Метрика описывает массовую, но
не объёмную загрузку.

## 14. Route deviation rate

```text
distance_deviation_pct =
    (distance_actual_km - distance_planned_km)
    / nullif(distance_planned_km, 0)
```

Дополнительно:

```text
route_deviation_rate =
    count(distance_deviation_pct > threshold) / count(eligible deliveries)
```

Порог фиксируется до анализа, например 10%, и проверяется на чувствительность.

## 15. Event-attributed delay share

```text
event_attributed_delay_share =
    sum(route_events.delay_minutes) / nullif(delay_minutes, 0)
```

Рассчитывается на уровне доставки после агрегации событий. Значения выше 1
возможны из-за параллельных событий или экспертной оценки; их нельзя
автоматически трактовать как ошибку без проверки.

## 16. Failed delivery rate

Защитная метрика:

```text
failed_delivery_rate =
    count(delivery_status = 'failed')
    / count(deliveries in terminal status)
```

Терминальные статусы: `delivered`, `failed`, `cancelled`; отмены также
показываются отдельно, чтобы не маскировать проблему.

## 17. Vehicle breakdown rate

```text
vehicle_breakdown_rate =
    count(distinct deliveries with event_type = 'breakdown')
    / count(deliveries)
```

Срезы: автомобиль, тип, возрастная группа и период.

## 18. Maintenance downtime rate

```text
maintenance_downtime_rate =
    sum(downtime_hours)
    / available_fleet_hours_in_period
```

Знаменатель требует календаря доступности автомобиля. До его реализации можно
показывать `downtime_hours` как диагностическую метрику, но не называть долей.

## 19. Breakdowns per 10k km

Частота поломок с нормализацией на фактический пробег:

```text
breakdowns_per_10k_km =
    count(breakdown events) / sum(distance_actual_km) * 10000
```

Зерно результата: автомобиль × период или сопоставимая группа × период. В
знаменатель входят завершённые рейсы с известным положительным километражем;
числитель относится к той же экспозиции. Повторные записи одного инцидента
предварительно дедуплицируются.

## 20. Breakdowns per 1000 trip hours

Частота поломок с нормализацией на время эксплуатации в рейсах:

```text
trip_hours =
    date_diff('minute', actual_departure_at, actual_delivery_at) / 60

breakdowns_per_1000_trip_hours =
    count(breakdown events) / sum(trip_hours) * 1000
```

В знаменатель входят завершённые рейсы с валидными фактическими временами.
Поломка незавершённого рейса учитывается только при наличии отдельной
достоверной экспозиции до события; иначе она отражается в контроле неполноты.

## 21. Data completeness rate

Защитная метрика качества:

```text
data_completeness_rate =
    1 - missing_required_values / expected_required_values
```

Набор обязательных полей фиксируется отдельно для каждого статуса. Метрика
публикуется рядом с KPI, если пропуски могут изменить вывод.

## Срезы и минимальный размер группы

Основные срезы:

- маршрут и регионы;
- клиент и сегмент;
- тип груза и приоритет;
- водитель;
- автомобиль, тип и возраст;
- день недели, месяц и сезон;
- наличие и тип события.

Малые группы не ранжируются без указания размера выборки. Минимальный порог
будет выбран до анализа; рекомендуется показывать объём и доверительный интервал
даже после фильтрации.

## Цели

Числовые цели на этапе проектирования не задаются: отсутствует базовый период.
После генерации данных нужно:

1. зафиксировать baseline;
2. оценить вариативность по периодам;
3. выбрать операционно достижимый диапазон;
4. определить основную цель, драйверы и защитные метрики;
5. не подгонять цель под заранее сгенерированный результат.
