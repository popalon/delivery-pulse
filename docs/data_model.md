# Модель данных DeliveryPulse

## Общие принципы

- Модель логическая и не привязана к конкретной СУБД.
- Типы приведены в форме, совместимой по смыслу с DuckDB.
- Все временные метки хранятся в UTC. Бизнес-часовой пояс первого релиза —
  `Europe/Moscow`; он используется для календарных срезов и отображения.
- Денежные значения используют `DECIMAL(14, 2)`.
- Единственная валюта первого релиза — RUB.
- `NULL` в финансовом поле означает неизвестное значение, `0` — известное
  отсутствие соответствующих затрат. Неизвестные значения не заменяются нулями.
- `route_code` хранится в справочнике маршрутов и является стабильным кодом
  бизнес-направления, а не геометрией GPS-трека.
- Удаление родительских записей при наличии дочерних запрещено.
- Для учебной аналитики один заказ исполняется одной доставкой; связь
  `orders` → `deliveries` оставлена 1:0..1, чтобы сохранять отменённые и ещё не
  назначенные заказы.

## Связи

```text
routes    1 ─── N orders
customers 1 ─── N orders 1 ─── 0..1 deliveries N ─── 1 drivers
                                      │       └─────── 1 vehicles
                                      │
                                      └──── 0..N route_events

vehicles 1 ─── 0..N maintenance
```

## `routes`

Назначение: справочник устойчивых направлений с нормативным расстоянием и
временем в пути.

Зерно: одна строка на направленную пару регионов и класс маршрута.

| Поле | Тип | Обязательное | Описание |
|---|---|---:|---|
| `route_id` | `BIGINT` | да | Идентификатор маршрута |
| `route_code` | `VARCHAR` | да | Стабильный бизнес-код направления |
| `origin_region` | `VARCHAR` | да | Регион отправления |
| `destination_region` | `VARCHAR` | да | Регион назначения |
| `standard_distance_km` | `DECIMAL(10, 2)` | да | Нормативное расстояние |
| `standard_transit_hours` | `DECIMAL(8, 2)` | да | Нормативное время в пути |
| `route_class` | `VARCHAR` | да | `regional`, `interregional`, `long_haul` |
| `is_active` | `BOOLEAN` | да | Доступен ли маршрут для новых заказов |

Первичный ключ: `route_id`.

Внешние ключи: нет.

Ограничения:

- `route_code` уникален;
- `origin_region <> destination_region`;
- `standard_distance_km > 0` и `standard_transit_hours > 0`;
- комбинация `origin_region`, `destination_region`, `route_class` уникальна;
- `route_class` входит в заданный справочник;
- обратное направление является отдельным маршрутом.

## `customers`

Назначение: справочник заказчиков и их договорных условий.

Зерно: одна строка на клиента.

| Поле | Тип | Обязательное | Описание |
|---|---|---:|---|
| `customer_id` | `BIGINT` | да | Идентификатор клиента |
| `customer_name` | `VARCHAR` | да | Синтетическое отображаемое имя |
| `customer_segment` | `VARCHAR` | да | `small`, `medium`, `enterprise` |
| `industry` | `VARCHAR` | да | Синтетическая отрасль |
| `contract_start_date` | `DATE` | да | Начало договора |
| `contract_end_date` | `DATE` | нет | Окончание договора |
| `default_sla_hours` | `SMALLINT` | да | Базовый срок доставки |
| `payment_terms_days` | `SMALLINT` | да | Срок оплаты |
| `is_active` | `BOOLEAN` | да | Активен ли клиент |

Первичный ключ: `customer_id`.

Внешние ключи: нет.

Ограничения:

- `customer_name` уникален в синтетическом наборе;
- `default_sla_hours > 0`;
- `payment_terms_days >= 0`;
- `contract_end_date IS NULL OR contract_end_date >= contract_start_date`;
- значения `customer_segment` входят в заданный справочник.

## `drivers`

Назначение: справочник водителей и характеристик, влияющих на назначение рейса.

Зерно: одна строка на водителя.

| Поле | Тип | Обязательное | Описание |
|---|---|---:|---|
| `driver_id` | `BIGINT` | да | Идентификатор водителя |
| `driver_code` | `VARCHAR` | да | Неперсональный синтетический код |
| `hire_date` | `DATE` | да | Дата найма |
| `experience_years` | `DECIMAL(4, 1)` | да | Стаж до начала датасета |
| `license_class` | `VARCHAR` | да | Категория допуска |
| `home_region` | `VARCHAR` | да | Базовый регион |
| `employment_status` | `VARCHAR` | да | `active`, `leave`, `terminated` |

Первичный ключ: `driver_id`.

Внешние ключи: нет.

Ограничения:

- `driver_code` уникален;
- `experience_years >= 0`;
- `hire_date` не позже даты окончания наблюдений;
- `license_class` и `employment_status` входят в справочники.

## `vehicles`

Назначение: справочник транспортных средств и их эксплуатационных параметров.

Зерно: одна строка на автомобиль.

| Поле | Тип | Обязательное | Описание |
|---|---|---:|---|
| `vehicle_id` | `BIGINT` | да | Идентификатор автомобиля |
| `vehicle_code` | `VARCHAR` | да | Синтетический код автопарка |
| `vehicle_type` | `VARCHAR` | да | `van`, `truck`, `refrigerated_truck` |
| `capacity_kg` | `DECIMAL(10, 2)` | да | Допустимая масса груза |
| `manufacture_year` | `SMALLINT` | да | Год выпуска |
| `fuel_type` | `VARCHAR` | да | Тип топлива |
| `fuel_consumption_l_100km` | `DECIMAL(6, 2)` | да | Нормативный расход |
| `odometer_at_observation_start_km` | `DECIMAL(12, 2)` | да | Начальный пробег |
| `home_region` | `VARCHAR` | да | Базовый регион |
| `service_status` | `VARCHAR` | да | `active`, `maintenance`, `retired` |

Первичный ключ: `vehicle_id`.

Внешние ключи: нет.

Ограничения:

- `vehicle_code` уникален;
- `capacity_kg > 0`;
- `fuel_consumption_l_100km > 0`;
- `odometer_at_observation_start_km >= 0`;
- `manufacture_year` находится в разумном диапазоне и не позже года датасета;
- категориальные поля входят в справочники.

## `orders`

Назначение: коммерческое обязательство клиента, тариф и требования к доставке.

Зерно: одна строка на заказ.

| Поле | Тип | Обязательное | Описание |
|---|---|---:|---|
| `order_id` | `BIGINT` | да | Идентификатор заказа |
| `customer_id` | `BIGINT` | да | Клиент |
| `route_id` | `BIGINT` | да | Маршрут из справочника |
| `created_at` | `TIMESTAMP` | да | Создание заказа, UTC |
| `requested_pickup_at` | `TIMESTAMP` | да | Запрошенное время подачи |
| `promised_delivery_at` | `TIMESTAMP` | да | Договорный дедлайн |
| `cargo_type` | `VARCHAR` | да | Тип груза |
| `cargo_weight_kg` | `DECIMAL(10, 2)` | да | Масса груза |
| `distance_planned_km` | `DECIMAL(10, 2)` | да | Плановое расстояние |
| `quoted_revenue` | `DECIMAL(14, 2)` | да | Согласованная выручка |
| `priority` | `VARCHAR` | да | `standard`, `express` |
| `order_status` | `VARCHAR` | да | `created`, `assigned`, `completed`, `cancelled` |

Первичный ключ: `order_id`.

Внешние ключи:

- `customer_id` → `customers.customer_id`.
- `route_id` → `routes.route_id`.

Ограничения:

- `created_at <= requested_pickup_at < promised_delivery_at`;
- `cargo_weight_kg > 0`, `distance_planned_km > 0`, `quoted_revenue >= 0`;
- маршрут активен на момент создания нового заказа;
- `distance_planned_km` — план конкретного заказа и может отличаться от
  `routes.standard_distance_km`;
- категория груза, приоритет и статус входят в справочники;
- отменённый заказ не имеет завершённой доставки.

## `deliveries`

Назначение: фактическое исполнение заказа, назначенные ресурсы, время и
экономика.

Зерно: одна строка на попытку исполнения заказа; в первом релизе — не более
одной строки на заказ.

| Поле | Тип | Обязательное | Описание |
|---|---|---:|---|
| `delivery_id` | `BIGINT` | да | Идентификатор доставки |
| `order_id` | `BIGINT` | да | Исполняемый заказ |
| `driver_id` | `BIGINT` | да | Назначенный водитель |
| `vehicle_id` | `BIGINT` | да | Назначенный автомобиль |
| `planned_departure_at` | `TIMESTAMP` | да | Плановый выезд |
| `actual_departure_at` | `TIMESTAMP` | нет | Фактический выезд |
| `actual_delivery_at` | `TIMESTAMP` | нет | Фактическое завершение |
| `distance_actual_km` | `DECIMAL(10, 2)` | нет | Фактическое расстояние |
| `delivery_status` | `VARCHAR` | да | `planned`, `in_transit`, `delivered`, `failed`, `cancelled` |
| `fuel_cost` | `DECIMAL(14, 2)` | нет | Топливные затраты |
| `driver_cost` | `DECIMAL(14, 2)` | нет | Затраты на водителя |
| `toll_cost` | `DECIMAL(14, 2)` | нет | Платные дороги |
| `maintenance_allocated_cost` | `DECIMAL(14, 2)` | нет | Распределённые затраты ТО |
| `other_cost` | `DECIMAL(14, 2)` | нет | Прочие прямые затраты |
| `penalty_amount` | `DECIMAL(14, 2)` | нет | Штраф или скидка за SLA |

Первичный ключ: `delivery_id`.

Внешние ключи:

- `order_id` → `orders.order_id`;
- `driver_id` → `drivers.driver_id`;
- `vehicle_id` → `vehicles.vehicle_id`.

Ограничения:

- `order_id` уникален в первом релизе;
- денежные компоненты и `penalty_amount >= 0`;
- `distance_actual_km > 0`, если заполнено;
- `actual_departure_at >= planned_departure_at - допустимое_раннее_окно`;
- `actual_delivery_at >= actual_departure_at`;
- статус `delivered` требует оба фактических времени и фактическое расстояние;
- незавершённые статусы не должны иметь `actual_delivery_at`;
- масса заказа обычно не превышает `vehicles.capacity_kg`; редкие реальные
  операционные перегрузы ограничены 5%, остаются в аналитической выборке и
  отличаются от искусственных дефектов качества.

### Полнота финансовых данных

Для расчёта полной маржи обязательны `orders.quoted_revenue`,
`deliveries.penalty_amount`, `deliveries.fuel_cost`, `deliveries.driver_cost`,
`deliveries.toll_cost`, `deliveries.maintenance_allocated_cost`,
`deliveries.other_cost` и агрегированная сумма `route_events.extra_cost`.

Каждое значение должно быть известно, включая явно записанный `0`. Если хотя бы
одно поле равно `NULL`, `total_delivery_cost`, `delivery_profit` и `margin_pct`
для доставки равны `NULL`; строка исключается из метрик полной прибыльности и
попадает в контроль полноты.

## Матрица статусов заказа и доставки

`—` означает, что доставка ещё не создана.

| `order_status` | Допустимый `delivery_status` | Правило |
|---|---|---|
| `created` | `—` | Заказ принят, исполнение ещё не назначено |
| `assigned` | `planned`, `in_transit` | Ресурсы назначены, исполнение не завершено |
| `completed` | `delivered` | Успешное вручение |
| `completed` | `failed` | Попытка завершена неуспешно, заказ закрыт без вручения |
| `cancelled` | `—`, `cancelled` | Отмена до создания или после назначения доставки |

Дополнительные правила:

- `failed` — терминальный статус доставки; требует документированной причины и
  не допускает `actual_delivery_at`;
- `cancelled` — терминальный статус отмены, а не неуспешной попытки; он не
  участвует в SLA завершённых доставок и не приравнивается к `failed`;
- доставка `cancelled` требует заказ `cancelled`;
- заказ `cancelled` не может иметь доставку `delivered` или `failed`;
- переход из терминального статуса запрещён без корректирующей записи;
- недопустимые сочетания являются критической ошибкой качества.

## `route_events`

Назначение: события в ходе доставки, объясняющие отклонения времени и затрат.

Зерно: одно событие на доставке.

| Поле | Тип | Обязательное | Описание |
|---|---|---:|---|
| `event_id` | `BIGINT` | да | Идентификатор события |
| `delivery_id` | `BIGINT` | да | Доставка |
| `event_at` | `TIMESTAMP` | да | Начало события |
| `event_end_at` | `TIMESTAMP` | нет | Окончание события |
| `event_type` | `VARCHAR` | да | Тип события |
| `severity` | `VARCHAR` | да | `low`, `medium`, `high` |
| `delay_minutes` | `INTEGER` | да | Оценка добавленной задержки |
| `extra_cost` | `DECIMAL(14, 2)` | да | Дополнительные прямые затраты |
| `region` | `VARCHAR` | да | Регион события |
| `notes_code` | `VARCHAR` | нет | Неперсональный код уточнения |

Первичный ключ: `event_id`.

Внешние ключи:

- `delivery_id` → `deliveries.delivery_id`.

Ограничения:

- `event_type` входит в справочник, например `traffic`, `weather`,
  `loading_delay`, `unloading_delay`, `breakdown`, `route_deviation`;
- `delay_minutes >= 0`, `extra_cost >= 0`;
- `event_end_at IS NULL OR event_end_at >= event_at`;
- событие находится между фактическим выездом и завершением либо явно относится
  к предрейсовой задержке;
- комбинация `delivery_id`, `event_at`, `event_type` не дублируется.

## `maintenance`

Назначение: история планового и внепланового обслуживания автомобилей.

Зерно: одно обслуживание или ремонт автомобиля.

| Поле | Тип | Обязательное | Описание |
|---|---|---:|---|
| `maintenance_id` | `BIGINT` | да | Идентификатор обслуживания |
| `vehicle_id` | `BIGINT` | да | Автомобиль |
| `maintenance_type` | `VARCHAR` | да | `scheduled`, `repair`, `inspection` |
| `started_at` | `TIMESTAMP` | да | Начало работ |
| `completed_at` | `TIMESTAMP` | нет | Завершение работ |
| `odometer_km` | `DECIMAL(12, 2)` | да | Пробег на момент работ |
| `cost_amount` | `DECIMAL(14, 2)` | да | Стоимость |
| `downtime_hours` | `DECIMAL(10, 2)` | нет | Продолжительность недоступности |
| `issue_category` | `VARCHAR` | нет | Категория неисправности |
| `maintenance_status` | `VARCHAR` | да | `scheduled`, `in_progress`, `completed`, `cancelled` |

Первичный ключ: `maintenance_id`.

Внешние ключи:

- `vehicle_id` → `vehicles.vehicle_id`.

Ограничения:

- `cost_amount >= 0`, `odometer_km >= 0`, `downtime_hours >= 0`;
- `completed_at >= started_at`, если заполнено;
- статус `completed` требует `completed_at` и `downtime_hours`;
- пробег автомобиля не уменьшается со временем;
- интервалы обслуживания одного автомобиля не должны необъяснимо
  перекрываться;
- автомобиль не назначается на рейс во время недоступности.

История `maintenance` обязательно содержит последнее завершённое обслуживание
до начала периода наблюдения для каждого активного автомобиля. Его
`completed_at` и `odometer_km` вместе с начальным пробегом автомобиля и
фактическим километражем рейсов позволяют вычислить время и километры после
предыдущего обслуживания. Предпериодная запись нужна как стартовое состояние;
её стоимость не включается в расходы анализируемого периода.

## Производные признаки, не хранимые в исходных таблицах

Следующие поля вычисляются в витринах:

- `is_on_time`;
- `delay_minutes`;
- `total_delivery_cost`;
- `delivery_profit`;
- `margin_pct`;
- `cost_per_actual_km`;
- `capacity_utilization`;
- `route_event_count`;
- `event_delay_minutes`;
- `days_since_last_maintenance`;
- `km_since_last_maintenance`;
- `trip_hours`.

Это предотвращает расхождение между сохранённым и пересчитанным значением.

## Операционные перегрузы и технические дефекты

Реальный операционный перегруз — намеренно сгенерированное бизнес-событие, при
котором корректные `cargo_weight_kg` и `capacity_kg` дают
`capacity_utilization > 1`. Такая строка остаётся в аналитической выборке.

Искусственный дефект качества — намеренно испорченное значение только для
проверок data quality. Генератор записывает реестр таких дефектов в:

```text
data/metadata/quality_issues_manifest.csv
```

Запись manifest содержит минимум `table_name`, `record_id`, `field_name`,
`issue_type`, `expected_detection` и `description`. Seed и параметры запуска
хранятся рядом в `data/metadata/metadata.json`. Manifest:

- используется тестами для проверки обнаружения известных дефектов;
- не загружается в DuckDB-витрины и не читается аналитическим кодом;
- не применяется для фильтрации или «подсказки» аналитических результатов;
- является локальным сгенерированным артефактом и не коммитится в Git.

## Открытые проектные решения

- Зафиксировать допустимое окно раннего выезда.
- Решить, нужна ли во втором релизе модель нескольких попыток доставки на заказ.
- Уточнить справочники регионов, типов груза и событий до генерации данных.
