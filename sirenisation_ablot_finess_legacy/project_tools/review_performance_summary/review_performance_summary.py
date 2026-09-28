"""Graphique de synthèse des performances globales des méthodes de rapprochement."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter

# -----------------------------------------------------------------------------
# Inputs Stage 05
# -----------------------------------------------------------------------------
EJ_SUMMARY_PATH = Path(
    "results/05_analyze_reviews/ej/ej_global_review_summary.xlsx"
)
EGE_SUMMARY_PATH = Path(
    "results/05_analyze_reviews/ege/ege_global_review_summary.xlsx"
)
SHEET_NAME = "global_review_summary"

OUTPUT_FILENAMES = {
    "EJ": "ej_review_performance_summary.png",
    "EGE": "ege_review_performance_summary.png",
}

# Libellés des métriques déjà calculées et calées par Stage 05.
INITIAL_CORRECT = "Initial correct"
ANS_COVERAGE = "ANS coverage"
ANS_CORRECT = "ANS correct when proposed"
ANS_FALLBACK_CORRECT = "ANS + Initial fallback correct"
ADRIEN_COVERAGE = "Adrien coverage"
ADRIEN_CORRECT = "Adrien correct when proposed"
ADRIEN_FALLBACK_CORRECT = "Adrien + Initial fallback correct"
ADRIEN_ONLY_COVERAGE = "Adrien — only proposal coverage"
ADRIEN_ONLY_CORRECT = "Adrien correct — only proposal, when applicable"
ADRIEN_ONLY_FALLBACK_CORRECT = "Adrien — only proposal + Initial fallback correct"

BAR_LABELS = [
    "Initial",
    "ANS",
    "ANS + Initial fallback",
    "Adrien",
    "Adrien + Initial fallback",
    "Adrien — only proposal",
    "Adrien — only proposal + Initial fallback",
]

CORRECT_COLOR = "#4C956C"
INCORRECT_COLOR = "#E07A5F"
UNCOVERED_COLOR = "#D9D9D9"
FIGSIZE = (11.0, 6.4)
DPI = 180


def clean_text(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().replace("", pd.NA)


def check_columns(df: pd.DataFrame, columns: list[str], path: Path) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise KeyError(f"{path}: colonnes manquantes: {missing}")


def parse_number(value: object, *, label: str) -> float:
    if pd.isna(value):
        raise ValueError(f"Valeur manquante pour {label!r}.")
    text = str(value).strip().replace(" ", "").replace("\u202f", "").replace(",", ".")
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"Valeur non numérique pour {label!r}: {value!r}") from exc


def load_global_summary(path: Path) -> pd.DataFrame:
    """Charge la feuille de résultats globaux produite par Stage 05."""
    # Lecture en string pour conserver les représentations Excel sans conversion implicite.
    df = pd.read_excel(path, sheet_name=SHEET_NAME, dtype="string")
    check_columns(
        df,
        ["Metric", "Population count", "Denominator", "Denominator population", "Basis"],
        path,
    )
    df = df.copy()
    df["Metric"] = clean_text(df["Metric"])

    duplicate_metrics = df.loc[df["Metric"].duplicated(keep=False), "Metric"].dropna()
    if not duplicate_metrics.empty:
        examples = ", ".join(sorted(set(duplicate_metrics.astype(str)))[:10])
        raise ValueError(f"{path}: métriques globales dupliquées: {examples}")
    return df


def metric_row(df: pd.DataFrame, metric: str, path: Path) -> pd.Series:
    rows = df.loc[df["Metric"].eq(metric)]
    if len(rows) != 1:
        raise ValueError(
            f"{path}: la métrique {metric!r} doit apparaître exactement une fois; "
            f"trouvé: {len(rows)}."
        )
    return rows.iloc[0]


def metric_count(df: pd.DataFrame, metric: str, path: Path) -> float:
    row = metric_row(df, metric, path)
    return parse_number(row["Population count"], label=f"{metric} / Population count")


def matchable_population(df: pd.DataFrame, path: Path) -> float:
    """Retourne la population estimée d'entités à rapprocher utilisée par Stage 05."""
    row = metric_row(df, INITIAL_CORRECT, path)
    total = parse_number(
        row["Denominator population"],
        label=f"{INITIAL_CORRECT} / Denominator population",
    )
    if total <= 0:
        raise ValueError(f"{path}: population à rapprocher non positive: {total}.")
    return total


def checked_parts(
    *,
    correct: float,
    covered: float,
    total: float,
    label: str,
) -> tuple[float, float, float]:
    """Construit correct / incorrect / non couvert et vérifie leur cohérence."""
    tolerance = max(0.02, total * 1e-9)
    if correct < -tolerance or covered < -tolerance:
        raise ValueError(f"{label}: effectif négatif inattendu.")
    if correct > covered + tolerance:
        raise ValueError(
            f"{label}: correct ({correct:.2f}) dépasse couvert ({covered:.2f})."
        )
    if covered > total + tolerance:
        raise ValueError(
            f"{label}: couvert ({covered:.2f}) dépasse la population à rapprocher "
            f"({total:.2f})."
        )

    correct = max(0.0, min(correct, total))
    covered = max(correct, min(covered, total))
    incorrect = covered - correct
    uncovered = total - covered
    return correct, incorrect, uncovered


def build_plot_data(df: pd.DataFrame, path: Path) -> tuple[pd.DataFrame, float]:
    """Construit les sept barres à partir des estimations globales Stage 05."""
    total = matchable_population(df, path)

    rows = []

    initial_correct = metric_count(df, INITIAL_CORRECT, path)
    rows.append(
        (BAR_LABELS[0],)
        + checked_parts(
            correct=initial_correct,
            covered=total,
            total=total,
            label=BAR_LABELS[0],
        )
    )

    ans_covered = metric_count(df, ANS_COVERAGE, path)
    ans_correct = metric_count(df, ANS_CORRECT, path)
    rows.append(
        (BAR_LABELS[1],)
        + checked_parts(
            correct=ans_correct,
            covered=ans_covered,
            total=total,
            label=BAR_LABELS[1],
        )
    )

    ans_fallback_correct = metric_count(df, ANS_FALLBACK_CORRECT, path)
    rows.append(
        (BAR_LABELS[2],)
        + checked_parts(
            correct=ans_fallback_correct,
            covered=total,
            total=total,
            label=BAR_LABELS[2],
        )
    )

    adrien_covered = metric_count(df, ADRIEN_COVERAGE, path)
    adrien_correct = metric_count(df, ADRIEN_CORRECT, path)
    rows.append(
        (BAR_LABELS[3],)
        + checked_parts(
            correct=adrien_correct,
            covered=adrien_covered,
            total=total,
            label=BAR_LABELS[3],
        )
    )

    adrien_fallback_correct = metric_count(df, ADRIEN_FALLBACK_CORRECT, path)
    rows.append(
        (BAR_LABELS[4],)
        + checked_parts(
            correct=adrien_fallback_correct,
            covered=total,
            total=total,
            label=BAR_LABELS[4],
        )
    )

    adrien_only_covered = metric_count(df, ADRIEN_ONLY_COVERAGE, path)
    adrien_only_correct = metric_count(df, ADRIEN_ONLY_CORRECT, path)
    rows.append(
        (BAR_LABELS[5],)
        + checked_parts(
            correct=adrien_only_correct,
            covered=adrien_only_covered,
            total=total,
            label=BAR_LABELS[5],
        )
    )

    adrien_only_fallback_correct = metric_count(
        df, ADRIEN_ONLY_FALLBACK_CORRECT, path
    )
    rows.append(
        (BAR_LABELS[6],)
        + checked_parts(
            correct=adrien_only_fallback_correct,
            covered=total,
            total=total,
            label=BAR_LABELS[6],
        )
    )

    plot_data = pd.DataFrame(
        rows,
        columns=["Method", "Estimated correct", "Estimated incorrect", "Not covered"],
    )

    row_totals = plot_data[["Estimated correct", "Estimated incorrect", "Not covered"]].sum(axis=1)
    if not ((row_totals - total).abs() <= max(0.02, total * 1e-9)).all():
        raise ValueError(f"{path}: certaines barres ne somment pas à la population à rapprocher.")

    return plot_data, total


def format_count(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ")


def annotate_segments(ax, plot_data: pd.DataFrame, total: float) -> None:
    columns = ["Estimated correct", "Estimated incorrect", "Not covered"]
    for y, row in plot_data.iterrows():
        left = 0.0
        for column in columns:
            value = float(row[column])
            share = value / total if total else 0.0
            if share >= 0.045:
                ax.text(
                    left + value / 2,
                    y,
                    f"{100 * share:.1f}%\nN≈{format_count(value)}",
                    ha="center",
                    va="center",
                    fontsize=8.2,
                )
            elif value > 0:
                ax.text(
                    left + value / 2,
                    y,
                    f"{100 * share:.1f}%",
                    ha="center",
                    va="center",
                    fontsize=7.5,
                )
            left += value


def plot_summary(plot_data: pd.DataFrame, total: float, entity: str):
    """Produit un bar chart horizontal empilé de synthèse."""
    fig, ax = plt.subplots(figsize=FIGSIZE)
    y = list(range(len(plot_data)))

    correct = plot_data["Estimated correct"].astype(float)
    incorrect = plot_data["Estimated incorrect"].astype(float)
    uncovered = plot_data["Not covered"].astype(float)

    ax.barh(y, correct, label="Estimés corrects", color=CORRECT_COLOR)
    ax.barh(
        y,
        incorrect,
        left=correct,
        label="Estimés incorrects",
        color=INCORRECT_COLOR,
    )
    ax.barh(
        y,
        uncovered,
        left=correct + incorrect,
        label="Non couverts",
        color=UNCOVERED_COLOR,
    )

    ax.set_yticks(y)
    ax.set_yticklabels(plot_data["Method"])
    ax.invert_yaxis()
    ax.set_xlim(0, total)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: format_count(value)))
    ax.set_xlabel(f"Nombre estimé d'{entity} à rapprocher")
    ax.set_title(
        f"Performance globale des méthodes — {entity}\n"
        f"Population à rapprocher estimée : N≈{format_count(total)}"
    )
    ax.grid(axis="x", alpha=0.2)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.18), ncol=3, frameon=False)

    annotate_segments(ax, plot_data, total)
    fig.subplots_adjust(left=0.35, right=0.98, top=0.88, bottom=0.19)
    return fig


def generate_chart(summary_path: Path, output_path: Path, entity: str) -> None:
    summary = load_global_summary(summary_path)
    plot_data, total = build_plot_data(summary, summary_path)
    fig = plot_summary(plot_data, total, entity)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(output_path)


def infer_project_root() -> Path:
    # project_tools/review_performance_summary/review_performance_summary.py
    return Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Produit les graphiques EJ/EGE de synthèse à partir des résultats Stage 05."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Racine du dépôt. Par défaut, déduite de l'emplacement du script.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Répertoire de sortie. Par défaut: output/ à côté du script.",
    )
    args = parser.parse_args()

    project_root = (
        args.project_root.resolve() if args.project_root is not None else infer_project_root()
    )
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else Path(__file__).resolve().parent / "output"
    )

    inputs = {
        "EJ": project_root / EJ_SUMMARY_PATH,
        "EGE": project_root / EGE_SUMMARY_PATH,
    }

    for entity, summary_path in inputs.items():
        generate_chart(
            summary_path,
            output_dir / OUTPUT_FILENAMES[entity],
            entity,
        )


if __name__ == "__main__":
    main()
