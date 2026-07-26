# DeliveryPulse: decision register

Портфолио-проект не предполагает реального approval. Первоначальные статусы —
`proposed`, `monitoring` или `blocked_by_evidence`.

| ID | Rec | Решение | Статус | Основание | Пересмотр | Роли | Условие изменения |
|---|---|---|---|---|---|---|---|
| D1 | R1 | Express pilot | proposed | H2 supported | через 8–12 недель | operations, commercial, analytics, safety | KPI лучше без нарушения guardrails |
| D2 | R2 | Breakdown response pilot | proposed | H3 supported | через 8–12 недель | fleet, finance, analytics, safety | ниже loss/recovery при допустимой стоимости |
| D3 | R3 | Client review | proposed | H5 supported | после договорного цикла | commercial, finance, operations, analytics | adjusted profit лучше без потери retention |
| D4 | R4 | Измерять duration и проверить alerts | proposed | H1 secondary | через 8 недель | terminal operations, analytics | ниже p90 без ошибок/overtime |
| D5 | R5 | Накопить maintenance data | monitoring | H4 inconclusive | после ещё 12 месяцев | fleet data, maintenance, analytics | ≥95% полноты и достаточно exposure |
| D6 | R6 | Не менять overload policy | blocked_by_evidence | H6 inconclusive | после минимальных ячеек | safety, operations, analytics | ≥100 overload и ≥20 outcomes в сегменте |

Требуемые данные определены KPI и guardrails карточек. Решение масштабировать,
изменить или остановить pilot фиксируется будущей записью.
