"""Distribution du nombre d'EGE par EJ dans le périmètre FINESS étudié."""

from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.colors import to_rgb
from matplotlib.ticker import PercentFormatter

# -----------------------------------------------------------------------------
# Inputs du workflow
# -----------------------------------------------------------------------------
EGE_PATH = Path(
    "data/source/finess_etablissements/"
    "EtablissementsGeolocalises_2026_05_04.parquet"
)
EJ_PATH = Path(
    "results/02_build_strata_plan/ej/"
    "ej_siren_proposals_stratified.parquet"
)
REVIEWED_EJ_PATH = Path(
    "results/04_merge_reviews/ej/ej_all_confirmed_decisions.parquet"
)
EJ_ANALYSIS_PATH = Path(
    "results/05_analyze_reviews/ej/ej_strata_plan_review_analysis.xlsx"
)

EJ = "EJ"
SECTOR = "secteur_EJ"
EGE = "nofinesset"
PARENT_EJ = "nofinessej"
STRATUM = "stratum_id"
WEIGHT = "sampling_weight"

MAX_EGE_CATEGORY = 20
BLUE = "#1f77b4"
DARK_ORANGE = "#b65a00"
LIGHT_ORANGE = "#f2a65a"
FIGSIZE = (9.0, 4.8)
DPI = 160


def clean_text(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().replace("", pd.NA)


def check_columns(df: pd.DataFrame, columns: list[str], path: Path) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise KeyError(f"{path}: colonnes manquantes: {missing}")


def load_population(project_root: Path) -> pd.DataFrame:
    """Construit le périmètre EJ étudié avec secteur, strate et nombre d'EGE."""
    ej_path = project_root / EJ_PATH
    ege_path = project_root / EGE_PATH

    ej = pd.read_parquet(ej_path, columns=[EJ, SECTOR, STRATUM])
    ege = pd.read_parquet(ege_path, columns=[EGE, PARENT_EJ])
    check_columns(ej, [EJ, SECTOR, STRATUM], ej_path)
    check_columns(ege, [EGE, PARENT_EJ], ege_path)

    ej[EJ] = clean_text(ej[EJ])
    ej[SECTOR] = clean_text(ej[SECTOR]).fillna("Non renseigné")
    ej[STRATUM] = clean_text(ej[STRATUM])
    ege[EGE] = clean_text(ege[EGE])
    ege[PARENT_EJ] = clean_text(ege[PARENT_EJ])

    if ej[EJ].isna().any():
        raise ValueError(f"{ej_path}: la colonne EJ doit être complète.")
    if ej[STRATUM].isna().any():
        raise ValueError(f"{ej_path}: la colonne {STRATUM} doit être complète.")

    # La table de propositions peut contenir plusieurs lignes par EJ. Le secteur
    # et la strate doivent toutefois être uniques pour une même EJ.
    for column in (SECTOR, STRATUM):
        conflicts = ej.groupby(EJ)[column].nunique(dropna=False)
        if conflicts.gt(1).any():
            bad = ", ".join(conflicts[conflicts.gt(1)].index[:10])
            raise ValueError(
                f"{ej_path}: valeurs contradictoires de {column} pour certaines EJ: {bad}"
            )
    ej = ej.drop_duplicates(EJ)[[EJ, SECTOR, STRATUM]].copy()

    # Un EGE ne doit être compté qu'une fois. Si un identifiant est dupliqué,
    # il doit toujours pointer vers la même EJ.
    ege = ege.dropna(subset=[EGE])
    parent_counts = ege.groupby(EGE)[PARENT_EJ].nunique(dropna=True)
    if parent_counts.gt(1).any():
        bad = ", ".join(parent_counts[parent_counts.gt(1)].index[:10])
        raise ValueError(f"{ege_path}: EGE rattachés à plusieurs EJ: {bad}")
    ege = ege.drop_duplicates(EGE)

    # EJ_PATH définit directement le périmètre EJ étudié et sa stratification.
    # Les EGE hors de ce périmètre sont ignorés lors du comptage.
    counts = (
        ege.loc[ege[PARENT_EJ].isin(set(ej[EJ]))]
        .groupby(PARENT_EJ)
        .size()
    )
    population = ej.copy()
    population["ege_count"] = population[EJ].map(counts).fillna(0).astype("int64")

    # Les EJ sans EGE ont été retirées en Stage 00. Leur présence ici signalerait
    # des inputs provenant de deux exécutions différentes.
    zero_ege = population.loc[population["ege_count"].eq(0), EJ]
    if not zero_ege.empty:
        examples = ", ".join(zero_ege.head(10))
        raise ValueError(
            "Des EJ du périmètre étudié n'ont aucun EGE dans le fichier FINESS. "
            f"Exemples: {examples}"
        )

    return add_ege_category(population)


def load_samples(project_root: Path, population: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Charge l'échantillon brut puis lui rattache les poids Stage 05."""
    reviewed_path = project_root / REVIEWED_EJ_PATH
    analysis_path = project_root / EJ_ANALYSIS_PATH

    reviewed = pd.read_parquet(reviewed_path, columns=[EJ])
    reviewed[EJ] = clean_text(reviewed[EJ])
    if reviewed[EJ].isna().any() or reviewed[EJ].duplicated().any():
        raise ValueError(f"{reviewed_path}: la colonne EJ doit être complète et unique.")

    raw = reviewed.merge(
        population[[EJ, SECTOR, STRATUM, "ege_count", "ege_category"]],
        on=EJ,
        how="left",
        validate="one_to_one",
    )
    if raw[SECTOR].isna().any():
        bad = ", ".join(raw.loc[raw[SECTOR].isna(), EJ].head(10))
        raise ValueError(f"EJ examinées hors du périmètre étudié: {bad}")

    # Important: dtype="string" préserve les zéros initiaux de Stratum ID.
    stage05 = pd.read_excel(analysis_path, sheet_name="analysis", dtype="string")
    check_columns(stage05, ["Stratum ID", "Sampling weight"], analysis_path)
    weights = stage05[["Stratum ID", "Sampling weight"]].copy()
    weights[STRATUM] = clean_text(weights["Stratum ID"])
    weights[WEIGHT] = pd.to_numeric(
        weights["Sampling weight"].str.replace(",", ".", regex=False),
        errors="coerce",
    )
    weights = weights[[STRATUM, WEIGHT]].dropna(subset=[STRATUM])
    if weights[STRATUM].duplicated().any():
        raise ValueError(f"{analysis_path}: Stratum ID doit être unique.")
    if weights[WEIGHT].isna().any() or weights[WEIGHT].le(0).any():
        raise ValueError(f"{analysis_path}: Sampling weight invalide.")

    weighted = raw.merge(weights, on=STRATUM, how="left", validate="many_to_one")
    if weighted[WEIGHT].isna().any():
        bad = ", ".join(weighted.loc[weighted[WEIGHT].isna(), EJ].head(10))
        raise ValueError(f"Poids Stage 05 introuvable pour certaines EJ: {bad}")

    return raw, weighted


def categories() -> list[str]:
    return [str(i) for i in range(MAX_EGE_CATEGORY)] + [f"{MAX_EGE_CATEGORY}+"]


def add_ege_category(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ege_category"] = pd.Categorical(
        out["ege_count"].map(
            lambda n: f"{MAX_EGE_CATEGORY}+" if n >= MAX_EGE_CATEGORY else str(int(n))
        ),
        categories=categories(),
        ordered=True,
    )
    return out


def totals(df: pd.DataFrame, column: str, weight: str | None = None) -> pd.Series:
    if weight is None:
        return df.groupby(column, observed=False).size().astype(float)
    return df.groupby(column, observed=False)[weight].sum().astype(float)


def color_shades(base_color: str, n: int) -> list[tuple[float, float, float]]:
    base = to_rgb(base_color)
    if n <= 1:
        return [base]
    strengths = [1 - 0.42 * i / (n - 1) for i in range(n)]
    return [
        tuple((1 - strength) + strength * component for component in base)
        for strength in strengths
    ]


def format_number(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ")


def plot_sector_pie(
    df: pd.DataFrame,
    title: str,
    color: str,
    weight: str | None = None,
):
    data = totals(df, SECTOR, weight).sort_values(ascending=False)
    percentages = data / data.sum() * 100

    fig = plt.figure(figsize=FIGSIZE)
    ax = fig.add_axes([0.04, 0.10, 0.50, 0.78])
    wedges, _ = ax.pie(
        data,
        startangle=90,
        counterclock=False,
        colors=color_shades(color, len(data)),
        wedgeprops={"edgecolor": "white", "linewidth": 0.8},
    )
    ax.axis("equal")

    prefix = "N≈" if weight else "n="
    labels = [
        f"{sector} — {prefix}{format_number(value)} ({pct:.1f} %)"
        for sector, value, pct in zip(data.index, data.values, percentages.values)
    ]
    fig.legend(
        wedges,
        labels,
        loc="center left",
        bbox_to_anchor=(0.56, 0.50),
        frameon=False,
        fontsize=8.5,
    )
    fig.suptitle(title, fontsize=12, y=0.97)
    return fig


def plot_ege_bars(
    df: pd.DataFrame,
    title: str,
    color: str,
    weight: str | None = None,
):
    data = totals(df, "ege_category", weight).reindex(categories(), fill_value=0.0)
    percentages = data / data.sum() * 100 if data.sum() else data
    x = list(range(len(data)))

    fig = plt.figure(figsize=FIGSIZE)
    ax = fig.add_axes([0.08, 0.19, 0.90, 0.50])
    ax.bar(x, percentages, color=color, width=0.82)
    ax.set_xlim(-0.6, len(data) - 0.4)
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))
    ax.set_xticks(x)
    ax.set_xticklabels(data.index, rotation=45, ha="right")
    ax.set_xlabel("Nombre d’EGE rattachés par EJ")
    ax.set_ylabel("Part des EJ")
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(title, fontsize=12, y=0.97)

    count_prefix = "N≈" if weight else "n="
    for xpos, pct, value in zip(x, percentages, data):
        ax.text(
            xpos,
            1.035,
            f"{pct:.1f} %",
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="bottom",
            fontsize=8,
            clip_on=False,
        )
        # Le nombre reste incliné pour garder des barres étroites et lisibles.
        ax.text(
            xpos,
            1.115,
            f"{count_prefix}{format_number(value)}",
            transform=ax.get_xaxis_transform(),
            ha="right",
            va="bottom",
            rotation=-45,
            rotation_mode="anchor",
            fontsize=7.5,
            clip_on=False,
        )
    return fig


def safe_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "non_renseigne"


def save(fig, output_dir: Path, filename: str) -> None:
    path = output_dir / filename
    fig.savefig(path, dpi=DPI, facecolor="white")
    plt.close(fig)


def export_set(
    df: pd.DataFrame,
    *,
    output_dir: Path,
    prefix: str,
    label: str,
    color: str,
    sectors: list[str],
    weight: str | None = None,
) -> None:
    if weight:
        scope = f"n brut={len(df):,} ; N pondéré≈{format_number(df[weight].sum())}"
    else:
        scope = f"n={len(df):,}"

    charts = [
        (
            plot_sector_pie(df, f"{label} — EJ par secteur ({scope})", color, weight),
            f"{prefix}_ej_par_secteur.png",
        ),
        (
            plot_ege_bars(
                df,
                f"{label} — nombre d’EGE par EJ — tous secteurs ({scope})",
                color,
                weight,
            ),
            f"{prefix}_ege_par_ej_global.png",
        ),
    ]

    for fig, filename in charts:
        save(fig, output_dir, filename)

    width = max(2, len(str(len(sectors))))
    for i, sector in enumerate(sectors, 1):
        sector_df = df.loc[df[SECTOR].eq(sector)]
        fig = plot_ege_bars(
            sector_df,
            f"{label} — nombre d’EGE par EJ — secteur {sector}",
            color,
            weight,
        )
        filename = f"{prefix}_ege_par_ej_secteur_{i:0{width}d}_{safe_name(sector)}.png"
        save(fig, output_dir, filename)


def run(project_root: Path, output_dir: Path) -> None:
    population = load_population(project_root)
    raw_sample, weighted_sample = load_samples(project_root, population)
    sectors = totals(population, SECTOR).sort_values(ascending=False).index.tolist()

    output_dir.mkdir(parents=True, exist_ok=True)
    export_set(
        population,
        output_dir=output_dir,
        prefix="population",
        label="Population EJ étudiée",
        color=BLUE,
        sectors=sectors,
    )
    export_set(
        raw_sample,
        output_dir=output_dir,
        prefix="echantillon_brut",
        label="Échantillon EJ examiné — brut",
        color=DARK_ORANGE,
        sectors=sectors,
    )
    export_set(
        weighted_sample,
        output_dir=output_dir,
        prefix="echantillon_pondere",
        label="Échantillon EJ examiné — pondéré",
        color=LIGHT_ORANGE,
        sectors=sectors,
        weight=WEIGHT,
    )

    print(f"Population étudiée : {len(population):,} EJ")
    print(f"Échantillon examiné : {len(raw_sample):,} EJ")
    print(f"Total pondéré : {weighted_sample[WEIGHT].sum():,.2f} EJ")
    print(f"Graphiques : {output_dir.resolve()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        help="Racine du dépôt. Déduite automatiquement si le script est dans project_tools/.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Répertoire de sortie. Par défaut: output/ à côté du script.",
    )
    args = parser.parse_args()

    tool_dir = Path(__file__).resolve().parent
    project_root = args.project_root.resolve() if args.project_root else tool_dir.parents[1]
    output_dir = args.output_dir.resolve() if args.output_dir else tool_dir / "output"
    run(project_root, output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
