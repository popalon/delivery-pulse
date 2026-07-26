# DeliveryPulse: executive summary

На синтетических наблюдательных данных выделены три направления для управляемой
проверки: express-процесс, response на поломки и коммерческие условия крупных
клиентов. Это не причинные выводы и не прогноз; следующий шаг — ограниченные
pilots с контрольными группами.

## Три приоритета

1. **P1 — express pilot.** После контроля mix express сохраняет +6,22 п.п.
   риска опоздания. Проверить SLA, раннее назначение ресурсов и буферы.
2. **P1 — breakdown response.** Breakdown связан с тяжёлыми убытками. Проверить
   резервирование, скорость реакции, замену транспорта и контроль затрат.
3. **P2 — client review.** У 165 клиентов достаточного объёма различия прибыли
   сохраняются после контроля mix. Проверять условия вместе с риском retention.

## Пока нельзя

- менять интервалы ТО: H4 `inconclusive`;
- разрешать или запрещать перегруз по финансовому результату: H6
  `inconclusive`, safety limits сохраняются;
- масштабировать программу loading delay по факту события: H1 primary
  `not_supported`; допустим только pilot длительности.

KPI: express OTD и p90 delay; breakdown loss rate и recovery time; adjusted
client profit и group margin. Guardrails: standard OTD, безопасность, failed
rate, retention, объём и полная стоимость парка.

0–30 дней — baseline; 31–60 — pilots; 61–90 — scale/modify/stop. Сценарные
суммы редактируемы и помечены `illustrative_scenario_not_forecast`.
