"""Small quality-control calculations for dense expression datasets."""

from dataclasses import dataclass

import numpy as np

from cellscope.dataset import Dataset


@dataclass(frozen=True)
class QualityMetrics:
    """Per-cell and per-gene totals calculated from a Dataset."""

    cell_total_counts: np.ndarray
    cell_detected_genes: np.ndarray
    gene_total_counts: np.ndarray
    gene_detected_cells: np.ndarray

    def summary(self) -> str:
        """Return a compact report suitable for the Dataset page."""
        return (
            f"Cells: {len(self.cell_total_counts)}; "
            f"median counts {np.median(self.cell_total_counts):.1f}; "
            f"median detected genes {np.median(self.cell_detected_genes):.1f}\n"
            f"Genes: {len(self.gene_total_counts)}; "
            f"median counts {np.median(self.gene_total_counts):.1f}; "
            f"detected in {np.count_nonzero(self.gene_detected_cells)} genes"
        )


def calculate_quality_metrics(dataset: Dataset) -> QualityMetrics:
    """Calculate total counts and detected features for each cell and gene.

    A feature is detected when its count is greater than zero. Returned arrays
    are new float64/int64 arrays; the source dataset is never modified.
    """
    counts = dataset.counts
    if counts.ndim != 2 or counts.shape != (dataset.n_cells, dataset.n_genes):
        raise ValueError("Dataset counts must match its cell and gene labels.")
    detected = counts > 0
    return QualityMetrics(
        cell_total_counts=counts.sum(axis=1, dtype=np.float64),
        cell_detected_genes=detected.sum(axis=1, dtype=np.int64),
        gene_total_counts=counts.sum(axis=0, dtype=np.float64),
        gene_detected_cells=detected.sum(axis=0, dtype=np.int64),
    )


def filter_cells(
    dataset: Dataset, min_total_counts: int = 0, min_detected_genes: int = 0
) -> Dataset:
    """Return a dataset containing cells that meet both minimum thresholds.

    The input is not modified. At least one cell must remain; thresholds that
    remove every cell raise ``ValueError`` so an empty analysis cannot proceed.
    """
    if min_total_counts < 0 or min_detected_genes < 0:
        raise ValueError("Filter thresholds must be zero or greater.")
    metrics = calculate_quality_metrics(dataset)
    keep = (metrics.cell_total_counts >= min_total_counts) & (
        metrics.cell_detected_genes >= min_detected_genes
    )
    if not np.any(keep):
        raise ValueError("The selected thresholds would remove every cell.")
    return Dataset(
        counts=dataset.counts[keep].copy(),
        cell_ids=tuple(cell for cell, selected in zip(dataset.cell_ids, keep) if selected),
        gene_ids=dataset.gene_ids,
        source=dataset.source,
    )
