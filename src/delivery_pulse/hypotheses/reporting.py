"""Reports and matplotlib figures for formal hypothesis results."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import pandas as pd
from matplotlib.ticker import PercentFormatter

from delivery_pulse import __version__
from delivery_pulse.hypotheses.models import (
    FeasibilityResult,
    HypothesisResult,
)

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BLUE = "#3266A8"
ORANGE = "#D9782D"
GREY = "#D7DCE2"
INK = "#252A34"


def _save(fig: plt.Figure, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _effect_chart(
    result: HypothesisResult,
    path: Path,
    title: str,
) -> Path:
    values = [result.unadjusted_effect, result.adjusted_risk_difference]
    low = [result.unadjusted_ci_low, result.risk_difference_ci_low]
    high = [result.unadjusted_ci_high, result.risk_difference_ci_high]
    fig, ax = plt.subplots(figsize=(7.5, 4.4))
    positions = np.arange(2)
    for position, value, lower, upper, color in zip(
        positions, values, low, high, (BLUE, ORANGE), strict=True
    ):
        if value is None or lower is None or upper is None:
            continue
        ax.errorbar(
            value,
            position,
            xerr=[[value - lower], [upper - value]],
            fmt="o",
            color=color,
            capsize=4,
        )
    ax.axvline(0, color=INK, linestyle="--", linewidth=1)
    ax.set_yticks(positions, ["Нескорректированный", "Скорректированный"])
    ax.set_xlabel(f"Разница риска; n={result.observations}")
    ax.xaxis.set_major_formatter(PercentFormatter(1))
    ax.set_title(title)
    ax.grid(axis="x", color=GREY)
    ax.spines[["top", "right"]].set_visible(False)
    return _save(fig, path)


def build_figures(
    results: list[HypothesisResult],
    coefficients: pd.DataFrame,
    diagnostics: pd.DataFrame,
    output_dir: Path,
) -> dict[str, Path]:
    """Build the seven pre-specified hypothesis figures."""
    by_id = {result.hypothesis_id: result for result in results}
    paths = {
        "h1_effect": _effect_chart(
            by_id["H1"],
            output_dir / "01_h1_loading_delay.png",
            "H1: loading delay и риск опоздания",
        ),
        "h2_effect": _effect_chart(
            by_id["H2"],
            output_dir / "02_h2_express.png",
            "H2: express против standard",
        ),
        "h3_effect": _effect_chart(
            by_id["H3"],
            output_dir / "03_h3_breakdown_loss.png",
            "H3: breakdown и риск убытка",
        ),
    }
    h4 = coefficients.loc[
        (coefficients["hypothesis_id"] == "H4")
        & coefficients["term"].eq("had_scheduled_maintenance_previous_month")
        & coefficients["ci_low"].notna()
        & coefficients["ci_high"].notna()
    ].copy()
    fig, ax = plt.subplots(figsize=(7.5, 4.4))
    if not h4.empty:
        for column in ("estimate", "ci_low", "ci_high"):
            h4[column] = pd.to_numeric(h4[column], errors="coerce")
        h4 = h4.dropna(subset=["estimate", "ci_low", "ci_high"])
        h4["log_estimate"] = np.log10(h4["estimate"])
        h4["log_ci_low"] = np.log10(h4["ci_low"])
        h4["log_ci_high"] = np.log10(h4["ci_high"])
        ax.errorbar(
            h4["log_estimate"],
            np.arange(len(h4)),
            xerr=[
                h4["log_estimate"] - h4["log_ci_low"],
                h4["log_ci_high"] - h4["log_estimate"],
            ],
            fmt="o",
            color=BLUE,
            capsize=4,
        )
        ax.set_yticks(np.arange(len(h4)), h4["model_name"])
    ax.axvline(0, color=INK, linestyle="--")
    ax.set_xlabel(f"log10(IRR), полный 95% CI; n={by_id['H4'].observations}")
    ax.set_title("H4: нестабильная оценка профилактики — inconclusive")
    ax.grid(axis="x", color=GREY)
    ax.spines[["top", "right"]].set_visible(False)
    paths["h4_rates"] = _save(fig, output_dir / "04_h4_breakdown_rates.png")

    h5 = coefficients.loc[
        (coefficients["hypothesis_id"] == "H5")
        & (coefficients["model_name"] == "customer_fixed_effects_hc3")
        & coefficients["term"].str.startswith("C(customer_id)")
    ].copy()
    h5 = h5.reindex(h5["estimate"].abs().sort_values(ascending=False).index).head(15)
    h5 = h5.sort_values("estimate")
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.errorbar(
        h5["estimate"],
        np.arange(len(h5)),
        xerr=[h5["estimate"] - h5["ci_low"], h5["ci_high"] - h5["estimate"]],
        fmt="o",
        color=BLUE,
        capsize=3,
    )
    ax.axvline(0, color=INK, linestyle="--")
    ax.set_yticks(np.arange(len(h5)), h5["term"].str.extract(r"\[T\.(.+)\]")[0])
    ax.set_xlabel(f"Скорректированный эффект, RUB; n={by_id['H5'].observations}")
    ax.set_title("H5: крупнейшие клиентские fixed effects")
    ax.grid(axis="x", color=GREY)
    ax.spines[["top", "right"]].set_visible(False)
    paths["h5_clients"] = _save(fig, output_dir / "05_h5_customer_effects.png")

    h6_diagnostic = diagnostics.loc[diagnostics["hypothesis_id"] == "H6"]
    overload_losses = (
        by_id["H6"].events
        if h6_diagnostic.empty
        else int(float(h6_diagnostic.iloc[0]["value"]))
    )
    fig, ax = plt.subplots(figsize=(7.5, 4.4))
    ax.bar(
        ["overload", "normal"],
        [by_id["H6"].exposed, by_id["H6"].unexposed],
        color=[ORANGE, BLUE],
    )
    ax.set_yscale("log")
    ax.set_ylabel("Число доставок, log scale")
    ax.set_title(
        f"H6: размер заранее заданных групп; overload losses={overload_losses}"
    )
    ax.spines[["top", "right"]].set_visible(False)
    paths["h6_segments"] = _save(fig, output_dir / "06_h6_overload_cells.png")

    forest = [
        result
        for result in results
        if result.hypothesis_id in {"H1", "H2", "H3", "H4"}
        and result.status != "inconclusive"
        and result.adjusted_effect is not None
        and result.adjusted_ci_low is not None
        and result.adjusted_ci_high is not None
    ]
    fig, ax = plt.subplots(figsize=(8, 5))
    positions = np.arange(len(forest))
    values = np.array([item.adjusted_effect for item in forest], dtype=float)
    lows = np.array([item.adjusted_ci_low for item in forest], dtype=float)
    highs = np.array([item.adjusted_ci_high for item in forest], dtype=float)
    ax.errorbar(
        values,
        positions,
        xerr=[values - lows, highs - values],
        fmt="o",
        color=BLUE,
        capsize=4,
    )
    ax.axvline(1, color=INK, linestyle="--")
    ax.set_xscale("log")
    ax.set_yticks(positions, [item.hypothesis_id for item in forest])
    ax.set_xlabel("Adjusted OR/IRR, 95% CI (log scale)")
    ax.set_title("Основные скорректированные относительные эффекты")
    ax.grid(axis="x", color=GREY)
    ax.spines[["top", "right"]].set_visible(False)
    paths["forest"] = _save(fig, output_dir / "07_primary_forest.png")
    return paths


def write_outputs(
    output_dir: Path,
    results: list[HypothesisResult],
    feasibility: tuple[FeasibilityResult, ...],
    coefficients: pd.DataFrame,
    diagnostics: pd.DataFrame,
    figures: dict[str, Path],
    metadata: dict[str, Any],
) -> dict[str, Path]:
    """Write deterministic machine-readable and human-readable artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary": output_dir / "hypothesis_summary.json",
        "results": output_dir / "hypothesis_results.csv",
        "coefficients": output_dir / "model_coefficients.csv",
        "diagnostics": output_dir / "model_diagnostics.csv",
        "report": output_dir / "hypothesis_report.md",
    }
    result_frame = pd.DataFrame([result.to_dict() for result in results])
    result_frame.to_csv(paths["results"], index=False, lineterminator="\n")
    coefficients.sort_values(["hypothesis_id", "model_name", "term"]).to_csv(
        paths["coefficients"], index=False, lineterminator="\n"
    )
    diagnostics.sort_values(["hypothesis_id", "model_name", "diagnostic"]).to_csv(
        paths["diagnostics"], index=False, lineterminator="\n"
    )
    summary = {
        "project_version": __version__,
        "metadata": metadata,
        "feasibility": [asdict(item) for item in feasibility],
        "results": [result.to_dict() for result in results],
        "files": sorted(path.name for path in paths.values())
        + sorted(path.name for path in figures.values()),
    }
    paths["summary"].write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    lines = [
        "# DeliveryPulse: формальная проверка гипотез",
        "",
        "Данные синтетические; анализ наблюдательный и не устанавливает причинность.",
        "p-value не является размером эффекта. BH применена к основным H1–H6.",
        "",
        "## Результаты",
        "",
        "| ID | n | events | unadjusted | adjusted | 95% CI | "
        "p | BH p | practical | status |",
        "|---|---:|---:|---:|---:|---|---:|---:|---|---|",
    ]
    for result in results:
        raw = _format(result.unadjusted_effect)
        adjusted = _format(result.adjusted_effect)
        low = _format(result.adjusted_ci_low)
        high = _format(result.adjusted_ci_high)
        p_value = _format(result.p_value)
        adjusted_p = _format(result.p_value_adjusted)
        lines.append(
            f"| {result.hypothesis_id} | {result.observations} | "
            f"{result.events} | {raw} | {adjusted} | [{low}, {high}] | "
            f"{p_value} | {adjusted_p} | "
            f"{result.practically_significant} | {result.status} |"
        )
    lines.extend(
        [
            "",
            "## Диагностика и ограничения",
            "",
            "- Нестабильность, separation, малый EPV и warnings переводят "
            "результат в inconclusive.",
            "- H5 использует fixed effects без иерархического shrinkage.",
            "- H6 не моделируется при недостаточных interaction-ячейках.",
            "- `not_supported` не доказывает отсутствие эффекта.",
            "- Результаты зависят от заранее указанной спецификации модели.",
            "",
            "## Графики",
            "",
        ]
    )
    lines.extend(
        f"- [{name}](figures/{path.name})" for name, path in sorted(figures.items())
    )
    paths["report"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return paths


def _format(value: float | None) -> str:
    return "—" if value is None else f"{value:.6g}"
