"""Orchestration for reproducible exploratory analysis."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import pandas as pd

from delivery_pulse.analysis.charts import build_charts
from delivery_pulse.analysis.loader import (
    AnalysisContext,
    AnalysisLoadError,
    load_context,
    open_read_only,
)
from delivery_pulse.analysis.reporting import write_report
from delivery_pulse.analysis.segmentation import (
    customer_summary,
    event_comparisons,
    event_type_costs,
    profitability_segments,
    rank_table,
    route_summary,
    vehicle_age_summary,
    vehicle_summary,
    vehicle_type_summary,
)
from delivery_pulse.analysis.summaries import (
    daily_summary,
    monthly_summary,
    priority_summary,
    profitability_distribution,
)


class AnalysisError(RuntimeError):
    """Raised when the EDA pipeline cannot complete."""


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """Files and analytical tables produced by one EDA run."""

    context: AnalysisContext
    tables: dict[str, pd.DataFrame]
    figures: dict[str, Path]
    report_path: Path
    elapsed_seconds: float


def run_eda(
    database: Path,
    output_dir: Path,
    *,
    top_n: int = 10,
    min_group_size: int = 30,
    report_format: str = "markdown",
) -> AnalysisResult:
    """Validate a warehouse and create deterministic descriptive EDA outputs."""
    if top_n <= 0:
        raise AnalysisError("top_n must be positive")
    if min_group_size <= 0:
        raise AnalysisError("min_group_size must be positive")
    if report_format != "markdown":
        raise AnalysisError("only markdown report format is supported")
    started = perf_counter()
    try:
        context = load_context(database)
        connection = open_read_only(context.database)
        try:
            routes = route_summary(connection)
            customers = customer_summary(connection, min_group_size)
            vehicles = vehicle_summary(connection)
            tables = {
                "daily": daily_summary(connection),
                "monthly": monthly_summary(connection),
                "profitability": profitability_distribution(connection),
                "priority": priority_summary(connection),
                "routes": routes,
                "customers": customers,
                "event_comparisons": event_comparisons(connection),
                "event_type_costs": event_type_costs(connection),
                "profitability_segments": profitability_segments(connection),
                "vehicles": vehicles,
                "vehicle_types": vehicle_type_summary(connection),
                "vehicle_ages": vehicle_age_summary(vehicles),
            }
        finally:
            connection.close()
    except AnalysisLoadError as error:
        raise AnalysisError(str(error)) from error

    tables.update(
        {
            "route_loss_ranking": rank_table(
                routes, "loss_amount", top_n=top_n, ascending=False
            ),
            "route_margin_ranking": rank_table(
                routes,
                "group_margin_pct",
                top_n=top_n,
                ascending=True,
                min_group_size=min_group_size,
            ),
            "route_otd_ranking": rank_table(
                routes,
                "on_time_delivery_rate",
                top_n=top_n,
                ascending=True,
                min_group_size=min_group_size,
                sample_column="delivered_count",
            ),
            "route_p90_ranking": rank_table(
                routes,
                "p90_delay_minutes",
                top_n=top_n,
                ascending=False,
                min_group_size=min_group_size,
                sample_column="delivered_count",
            ),
            "route_breakdown_ranking": rank_table(
                routes,
                "breakdown_deliveries",
                top_n=top_n,
                ascending=False,
                min_group_size=min_group_size,
            ),
            "customer_loss_ranking": rank_table(
                customers, "loss_amount", top_n=top_n, ascending=False
            ),
            "customer_negative_margin": customers.loc[customers["group_margin_pct"] < 0]
            .sort_values(
                ["group_margin_pct", "deliveries_count", "customer_id"],
                ascending=[True, False, True],
            )
            .head(top_n)
            .reset_index(drop=True),
            "customer_large_low_margin": customers.loc[
                customers["volume_band"] == "large_sample"
            ]
            .sort_values(
                ["group_margin_pct", "deliveries_count", "customer_id"],
                ascending=[True, False, True],
            )
            .head(top_n)
            .reset_index(drop=True),
            "customer_high_express": customers.sort_values(
                ["express_share", "deliveries_count", "customer_id"],
                ascending=[False, False, True],
            )
            .head(top_n)
            .reset_index(drop=True),
            "customer_small_sample": customers.loc[
                customers["volume_band"] == "small_sample"
            ]
            .sort_values(
                ["deliveries_count", "customer_id"],
                ascending=[True, True],
            )
            .reset_index(drop=True),
            "vehicle_breakdown_count_ranking": rank_table(
                vehicles,
                "breakdown_count",
                top_n=top_n,
                ascending=False,
            ),
            "vehicle_breakdown_ranking": rank_table(
                vehicles,
                "breakdowns_per_10k_km",
                top_n=top_n,
                ascending=False,
                min_group_size=10_000,
                sample_column="actual_distance_km",
            ),
        }
    )
    output = output_dir.resolve()
    figure_paths = build_charts(tables, output / "figures" / "eda", top_n)
    report_path = write_report(
        context,
        tables,
        figure_paths,
        output / "eda_summary.md",
        min_group_size=min_group_size,
    )
    return AnalysisResult(
        context=context,
        tables=tables,
        figures=figure_paths,
        report_path=report_path,
        elapsed_seconds=perf_counter() - started,
    )
