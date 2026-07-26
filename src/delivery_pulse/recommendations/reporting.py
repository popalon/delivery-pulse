# ruff: noqa: E501
"""Deterministic reports and decision-oriented figures."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import pandas as pd

from delivery_pulse.recommendations.models import Recommendation

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BLUE, ORANGE, GREY, INK = "#3266A8", "#D9782D", "#D7DCE2", "#252A34"


def recommendation_frame(items: tuple[Recommendation, ...]) -> pd.DataFrame:
    """Flatten cards for CSV while retaining readable collections."""
    rows = []
    for item in items:
        row = item.to_dict()
        for key, value in tuple(row.items()):
            if isinstance(value, tuple):
                row[key] = "|".join(value)
        rows.append(row)
    return pd.DataFrame(rows).sort_values("recommendation_id")


def decision_rows(items: tuple[Recommendation, ...]) -> pd.DataFrame:
    """Create an initial portfolio decision register."""
    rows = []
    for item in items:
        status = (
            "blocked_by_evidence"
            if item.priority == "HOLD"
            else (
                "monitoring" if item.action_type == "collect_more_data" else "proposed"
            )
        )
        rows.append(
            {
                "decision_id": f"D{item.recommendation_id[1:]}",
                "recommendation_id": item.recommendation_id,
                "current_decision": item.recommended_action,
                "status": status,
                "basis": f"{','.join(item.supporting_hypotheses)}; {item.evidence_level}",
                "review_period": item.review_period,
                "required_data": "|".join(item.target_kpis),
                "participant_roles": f"{item.owner_role}|finance_partner|data_analyst",
                "change_conditions": item.stop_conditions,
            }
        )
    return pd.DataFrame(rows)


def pilot_rows(items: tuple[Recommendation, ...]) -> pd.DataFrame:
    """Create pilot/measurement plans for all actionable cards."""
    rows = []
    for item in items:
        if item.priority not in {"P1", "P2"}:
            continue
        rows.append(
            {
                "recommendation_id": item.recommendation_id,
                "pilot_object": item.title,
                "comparison_group": "Сопоставимый текущий процесс без вмешательства",
                "duration": item.review_period,
                "minimum_volume": item.pilot_design,
                "primary_kpi": item.target_kpis[0],
                "guardrail": item.guardrail_metrics[0],
                "success_criterion": "Практически значимое улучшение KPI при соблюдении guardrails",
                "stop_criterion": item.stop_conditions,
                "owner_role": item.owner_role,
                "review_date": item.review_period,
                "implementation_risks": item.uncertainty,
            }
        )
    return pd.DataFrame(rows)


def build_figures(
    items: tuple[Recommendation, ...],
    scenarios: pd.DataFrame,
    output_dir: Path,
) -> dict[str, Path]:
    """Build five compact management figures."""
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = recommendation_frame(items)
    paths: dict[str, Path] = {}

    def save(fig: plt.Figure, name: str) -> None:
        path = output_dir / name
        fig.savefig(path, dpi=140, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        paths[name] = path

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(
        6 - frame["implementation_effort"],
        frame["confidence"],
        s=frame["priority_score"] * 5,
        color=BLUE,
    )
    for row in frame.itertuples():
        ax.annotate(
            row.recommendation_id, (6 - row.implementation_effort, row.confidence)
        )
    ax.set(
        xlabel="Impact proxy: обратная сложность (1–5)",
        ylabel="Confidence (1–5)",
        title="Impact × confidence",
    )
    ax.grid(color=GREY)
    save(fig, "01_impact_confidence.png")

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ordered = frame.sort_values(["priority_score", "recommendation_id"])
    ax.barh(ordered["recommendation_id"], ordered["priority_score"], color=BLUE)
    ax.set(xlabel="Priority score (0–100)", title="Приоритеты рекомендаций")
    save(fig, "02_priorities.png")

    fig, ax = plt.subplots(figsize=(8, 4.5))
    pivot = scenarios.pivot(
        index="recommendation_id", columns="scenario", values="net_effect_rub"
    )
    pivot[["conservative", "base", "optimistic"]].plot.bar(
        ax=ax, color=[GREY, BLUE, ORANGE]
    )
    ax.axhline(0, color=INK, linewidth=1)
    ax.set(
        ylabel="Иллюстративный net effect, RUB",
        xlabel="Recommendation",
        title="Сценарии — не прогноз",
    )
    save(fig, "03_scenarios.png")

    fig, ax = plt.subplots(figsize=(9, 5))
    matrix = pd.DataFrame(
        {
            item.recommendation_id: [len(item.target_kpis), len(item.guardrail_metrics)]
            for item in items
        },
        index=["KPI", "Guardrails"],
    )
    image = ax.imshow(matrix, cmap="Blues", aspect="auto")
    ax.set_xticks(range(len(matrix.columns)), matrix.columns)
    ax.set_yticks(range(2), matrix.index)
    for y in range(2):
        for x in range(len(matrix.columns)):
            ax.text(x, y, int(matrix.iloc[y, x]), ha="center", va="center")
    ax.set_title("KPI и guardrail matrix: число показателей")
    fig.colorbar(image, ax=ax)
    save(fig, "04_kpi_guardrails.png")

    fig, ax = plt.subplots(figsize=(9, 3.8))
    ax.barh(
        ["0–30", "31–60", "61–90"],
        [30, 30, 30],
        left=[0, 30, 60],
        color=[GREY, BLUE, ORANGE],
    )
    ax.set(xlabel="Дни", title="30/60/90 roadmap")
    ax.text(15, 0, "Измерения и baseline", ha="center", va="center")
    ax.text(45, 1, "Ограниченные pilots", ha="center", va="center", color="white")
    ax.text(75, 2, "Scale / modify / stop", ha="center", va="center")
    save(fig, "05_roadmap_30_60_90.png")
    return paths


def markdown_report(items: tuple[Recommendation, ...], scenarios: pd.DataFrame) -> str:
    """Render the local recommendation report."""
    lines = [
        "# DeliveryPulse — рекомендации",
        "",
        "> Синтетические наблюдательные данные. Сценарии — не финансовый прогноз.",
        "",
        "## Приоритетная матрица",
        "",
        "| ID | Evidence | Priority | Action | Score |",
        "|---|---|---|---|---:|",
    ]
    lines.extend(
        f"| {r.recommendation_id} | `{r.evidence_level}` | {r.priority} | `{r.action_type}` | {r.priority_score:.1f} |"
        for r in items
    )
    for item in items:
        lines.extend(
            [
                "",
                f"## {item.recommendation_id}. {item.title}",
                "",
                f"**Факт:** {item.observed_effect}",
                "",
                f"**Интерпретация и неопределённость:** {item.uncertainty}",
                "",
                f"**Действие:** {item.recommended_action}",
                "",
                f"**KPI:** {', '.join(item.target_kpis)}.",
                "",
                f"**Guardrails:** {', '.join(item.guardrail_metrics)}.",
                "",
                f"**Pilot:** {item.pilot_design}",
                "",
                f"**Ограничение:** {item.limitations}",
            ]
        )
    lines.extend(
        [
            "",
            "## Сценарии R1–R3",
            "",
            "Все предположения видимы в `scenario_analysis.csv`; снижение риска не выводится из OR.",
            "",
            "| Recommendation | Scenario | Coverage | Reduction assumption | Net effect, RUB |",
            "|---|---|---:|---:|---:|",
            "",
            "## 30/60/90",
            "",
            "- 0–30: измерения, выбор групп, baseline и guardrails.",
            "- 31–60: ограниченные pilots, еженедельный quality review, без расширения при ухудшении guardrails.",
            "- 61–90: решение scale, modify или stop, повторная проверка и обновление decision register.",
            "",
            "## Нельзя решать по текущим данным",
            "",
            "- Нельзя менять интервалы ТО на основании H4.",
            "- Нельзя разрешать или запрещать перегруз из-за финансового результата H6.",
            "- Нельзя масштабировать программу loading delay по бинарному primary H1.",
        ]
    )
    lines.extend(
        f"| {row.recommendation_id} | {row.scenario} | {row.coverage_share:.0%} | "
        f"{row.assumed_reduction_share:.0%} | {row.net_effect_rub:,.0f} |"
        for row in scenarios.itertuples()
    )
    return "\n".join(lines) + "\n"


def write_outputs(
    output_dir: Path,
    items: tuple[Recommendation, ...],
    scenarios: pd.DataFrame,
    figures: dict[str, Path],
    *,
    protocol_hash: str,
) -> dict[str, Path]:
    """Write all deterministic machine-readable artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    scores = recommendation_frame(items)
    pilots = pilot_rows(items)
    decisions = decision_rows(items)
    paths = {
        "json": output_dir / "recommendations.json",
        "scores": output_dir / "recommendation_scores.csv",
        "scenarios": output_dir / "scenario_analysis.csv",
        "pilots": output_dir / "pilot_plan.csv",
        "decisions": output_dir / "decision_register.csv",
        "report": output_dir / "recommendations_report.md",
    }
    payload = {
        "protocol_hash": protocol_hash,
        "scenario_label": "illustrative_scenario_not_forecast",
        "recommendations": [item.to_dict() for item in items],
        "files": sorted(path.name for path in [*paths.values(), *figures.values()]),
    }
    paths["json"].write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=list) + "\n",
        encoding="utf-8",
    )
    scores.to_csv(paths["scores"], index=False)
    scenarios.to_csv(paths["scenarios"], index=False)
    pilots.to_csv(paths["pilots"], index=False)
    decisions.to_csv(paths["decisions"], index=False)
    paths["report"].write_text(markdown_report(items, scenarios), encoding="utf-8")
    return paths
