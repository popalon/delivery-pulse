"""Matplotlib charts for the reproducible EDA report."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import PercentFormatter  # noqa: E402

BLUE = "#3266A8"
ORANGE = "#D9782D"
GOLD = "#C49A28"
INK = "#252A34"
GREY = "#D7DCE2"


def _save(fig: plt.Figure, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _finish_axis(ax: plt.Axes) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color=GREY, linewidth=0.7, alpha=0.7)
    ax.set_axisbelow(True)


def build_charts(
    tables: dict[str, pd.DataFrame],
    output_dir: Path,
    top_n: int,
) -> dict[str, Path]:
    """Build and save the ten required standalone EDA figures."""
    destination = output_dir.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    paths = {
        "monthly_deliveries": _monthly_deliveries(
            tables["monthly"], destination / "01_monthly_deliveries.png"
        ),
        "monthly_otd": _monthly_otd(
            tables["monthly"], destination / "02_monthly_otd.png"
        ),
        "monthly_profit_margin": _monthly_profit_margin(
            tables["monthly"], destination / "03_monthly_profit_margin.png"
        ),
        "route_loss_amount": _route_losses(
            tables["route_loss_ranking"],
            destination / "04_route_loss_amount.png",
            top_n,
        ),
        "route_otd": _route_otd(
            tables["route_otd_ranking"],
            destination / "05_route_otd.png",
            top_n,
        ),
        "customer_loss_amount": _customer_losses(
            tables["customer_loss_ranking"],
            destination / "06_customer_loss_amount.png",
            top_n,
        ),
        "profit_distribution": _profit_distribution(
            tables["profitability"],
            destination / "07_profit_distribution.png",
        ),
        "event_delays": _event_delays(
            tables["event_comparisons"],
            destination / "08_event_delays.png",
        ),
        "priority_comparison": _priority_comparison(
            tables["priority"],
            destination / "09_priority_comparison.png",
        ),
        "vehicle_breakdown_rate": _vehicle_breakdown_rate(
            tables["vehicle_types"],
            destination / "10_vehicle_breakdown_rate.png",
        ),
    }
    return paths


def _monthly_deliveries(frame: pd.DataFrame, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(9, 4.8))
    labels = pd.to_datetime(frame["calendar_month"]).dt.strftime("%Y-%m")
    ax.bar(labels, frame["deliveries_count"], color=BLUE, edgecolor=INK, linewidth=0.5)
    ax.set_title("Доставки по месяцам")
    ax.set_xlabel("Месяц, Europe/Moscow")
    ax.set_ylabel("Число доставок")
    ax.tick_params(axis="x", rotation=45)
    _finish_axis(ax)
    return _save(fig, path)


def _monthly_otd(frame: pd.DataFrame, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(9, 4.8))
    labels = pd.to_datetime(frame["calendar_month"]).dt.strftime("%Y-%m")
    ax.plot(
        labels,
        frame["on_time_delivery_rate"],
        color=BLUE,
        marker="o",
        linewidth=2,
    )
    ax.set_title("On-time delivery rate по месяцам")
    ax.set_xlabel("Месяц, Europe/Moscow")
    ax.set_ylabel("Доля доставленных вовремя")
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.set_ylim(0, 1.02)
    ax.tick_params(axis="x", rotation=45)
    _finish_axis(ax)
    return _save(fig, path)


def _monthly_profit_margin(frame: pd.DataFrame, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(9, 4.8))
    labels = pd.to_datetime(frame["calendar_month"]).dt.strftime("%Y-%m")
    ax.bar(
        labels,
        frame["total_delivery_profit"] / 1_000_000,
        color=BLUE,
        edgecolor=INK,
        linewidth=0.5,
        label="Прибыль",
    )
    margin_ax = ax.twinx()
    margin_ax.plot(
        labels,
        frame["group_margin_pct"],
        color=ORANGE,
        marker="s",
        linewidth=2,
        label="Групповая маржа",
    )
    ax.set_title("Прибыль и групповая маржа по месяцам")
    ax.set_xlabel("Месяц, Europe/Moscow")
    ax.set_ylabel("Прибыль, млн RUB")
    margin_ax.set_ylabel("Групповая маржа")
    margin_ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.tick_params(axis="x", rotation=45)
    _finish_axis(ax)
    margin_ax.spines["top"].set_visible(False)
    fig.legend(loc="upper center", ncol=2, frameon=False)
    return _save(fig, path)


def _route_losses(frame: pd.DataFrame, path: Path, top_n: int) -> Path:
    selected = frame.head(top_n).sort_values("loss_amount")
    fig, ax = plt.subplots(figsize=(8, 5.2))
    labels = selected["route_code"]
    ax.barh(labels, selected["loss_amount"] / 1_000, color=ORANGE, edgecolor=INK)
    ax.set_title(f"Топ-{len(selected)} маршрутов по сумме убытков")
    ax.set_xlabel("Сумма убытков, тыс. RUB")
    ax.set_ylabel("Маршрут")
    for index, (_, row) in enumerate(selected.iterrows()):
        ax.text(
            row["loss_amount"] / 1_000,
            index,
            f" n={int(row['deliveries_count'])}",
            va="center",
            fontsize=8,
        )
    _finish_axis(ax)
    return _save(fig, path)


def _route_otd(frame: pd.DataFrame, path: Path, top_n: int) -> Path:
    selected = frame.head(top_n).sort_values("on_time_delivery_rate", ascending=False)
    fig, ax = plt.subplots(figsize=(8, 5.2))
    ax.barh(
        selected["route_code"],
        selected["on_time_delivery_rate"],
        color=GOLD,
        edgecolor=INK,
    )
    ax.set_title("Маршруты с худшим OTD, минимум выборки применён")
    ax.set_xlabel("On-time delivery rate")
    ax.set_ylabel("Маршрут")
    ax.xaxis.set_major_formatter(PercentFormatter(1))
    ax.set_xlim(0, 1.02)
    for index, (_, row) in enumerate(selected.iterrows()):
        ax.text(
            row["on_time_delivery_rate"],
            index,
            f" n={int(row['delivered_count'])}",
            va="center",
            fontsize=8,
        )
    _finish_axis(ax)
    return _save(fig, path)


def _customer_losses(frame: pd.DataFrame, path: Path, top_n: int) -> Path:
    selected = frame.head(top_n).sort_values("loss_amount")
    fig, ax = plt.subplots(figsize=(8, 5.2))
    ax.barh(
        selected["customer_name"],
        selected["loss_amount"] / 1_000,
        color=ORANGE,
        edgecolor=INK,
    )
    ax.set_title(f"Топ-{len(selected)} клиентов по сумме убытков")
    ax.set_xlabel("Сумма убытков, тыс. RUB")
    ax.set_ylabel("Клиент")
    for index, (_, row) in enumerate(selected.iterrows()):
        ax.text(
            row["loss_amount"] / 1_000,
            index,
            f" n={int(row['deliveries_count'])}",
            va="center",
            fontsize=8,
        )
    _finish_axis(ax)
    return _save(fig, path)


def _profit_distribution(frame: pd.DataFrame, path: Path) -> Path:
    values = frame.loc[
        frame["financial_data_complete"] & frame["delivery_profit"].notna(),
        "delivery_profit",
    ]
    lower, upper = values.quantile([0.01, 0.99])
    outside = int(((values < lower) | (values > upper)).sum())
    shown = values.clip(lower, upper)
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.hist(shown, bins=35, color=BLUE, edgecolor="white")
    ax.axvline(0, color=INK, linewidth=1.2, linestyle="--")
    ax.set_title("Распределение прибыли доставки")
    ax.set_xlabel(
        f"Прибыль, RUB; показан диапазон p1–p99, за границей {outside} значений"
    )
    ax.set_ylabel("Число доставок")
    _finish_axis(ax)
    return _save(fig, path)


def _event_delays(frame: pd.DataFrame, path: Path) -> Path:
    selected = frame.loc[frame["comparison_group"] == "with"].copy()
    selected = selected.sort_values("p90_delay_minutes")
    positions = range(len(selected))
    fig, ax = plt.subplots(figsize=(9, 5.2))
    width = 0.38
    ax.barh(
        [position - width / 2 for position in positions],
        selected["median_delay_minutes"],
        height=width,
        color=BLUE,
        label="Медиана",
    )
    ax.barh(
        [position + width / 2 for position in positions],
        selected["p90_delay_minutes"],
        height=width,
        color=ORANGE,
        label="p90",
    )
    ax.set_yticks(list(positions), selected["event_type"])
    ax.set_title("Задержка доставок при наличии событий")
    ax.set_xlabel("Опоздание среди опоздавших, минуты")
    ax.set_ylabel("Тип события")
    ax.legend(frameon=False)
    _finish_axis(ax)
    return _save(fig, path)


def _priority_comparison(frame: pd.DataFrame, path: Path) -> Path:
    selected = frame.set_index("priority")
    metrics = [
        ("on_time_delivery_rate", "OTD"),
        ("group_margin_pct", "Маржа"),
        ("loss_making_delivery_rate", "Убыточные"),
    ]
    positions = list(range(len(metrics)))
    fig, ax = plt.subplots(figsize=(8, 4.8))
    width = 0.34
    for offset, (priority, color) in zip(
        (-width / 2, width / 2),
        (("standard", BLUE), ("express", ORANGE)),
        strict=True,
    ):
        values = [selected.loc[priority, column] for column, _ in metrics]
        ax.bar(
            [position + offset for position in positions],
            values,
            width=width,
            label=f"{priority}, n={int(selected.loc[priority, 'deliveries_count'])}",
            color=color,
        )
    ax.set_xticks(positions, [label for _, label in metrics])
    ax.set_title("Standard и express: SLA и экономика")
    ax.set_ylabel("Доля")
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.legend(frameon=False)
    _finish_axis(ax)
    return _save(fig, path)


def _vehicle_breakdown_rate(frame: pd.DataFrame, path: Path) -> Path:
    selected = frame.sort_values("breakdowns_per_10k_km", ascending=False)
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.bar(
        selected["vehicle_type"],
        selected["breakdowns_per_10k_km"],
        color=BLUE,
        edgecolor=INK,
    )
    ax.set_title("Поломки на 10 000 км по типу транспорта")
    ax.set_xlabel("Тип транспорта")
    ax.set_ylabel("Поломок на 10 000 км")
    for index, (_, row) in enumerate(selected.iterrows()):
        ax.text(
            index,
            row["breakdowns_per_10k_km"],
            f" {row['actual_distance_km'] / 1000:.0f} тыс. км",
            ha="center",
            va="bottom",
            fontsize=8,
        )
    _finish_axis(ax)
    return _save(fig, path)
