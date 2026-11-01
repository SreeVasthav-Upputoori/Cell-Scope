"""Hold a single-cell expression matrix in memory and read it from text files."""

from dataclasses import dataclass
import csv
import logging
from pathlib import Path

import numpy as np

# Delimiters are chosen by file extension so the format is explicit, not guessed.
_DELIMITERS = {".csv": ",", ".tsv": "\t", ".txt": "\t"}


class DatasetError(Exception):
    """Report a malformed or unreadable dataset in words suitable for a dialog.

    Raised instead of ValueError so a caller can tell an invalid file apart from
    a programming mistake. File system problems still propagate as OSError.
    """


@dataclass(frozen=True)
class Dataset:
    """An expression matrix with its cell and gene labels.

    ``counts`` is a two-dimensional float32 array holding one row per cell and
    one column per gene, matching the orientation used by AnnData. The label
    tuples are immutable, but the array is shared by reference and not copied;
    treat it as read-only while the GUI displays this dataset.

    This class stores measurements without interpreting them. It records no
    normalisation state, no quality-control flags, and no analysis results.
    """

    counts: np.ndarray
    cell_ids: tuple[str, ...]
    gene_ids: tuple[str, ...]
    source: Path

    @property
    def n_cells(self) -> int:
        """Return the number of rows, which is the number of cells."""
        return len(self.cell_ids)

    @property
    def n_genes(self) -> int:
        """Return the number of columns, which is the number of genes."""
        return len(self.gene_ids)

    def summary(self) -> str:
        """Return a short plain-text description for display; performs no analysis."""
        return (
            f"{self.source.name}\n"
            f"{self.n_cells} cells × {self.n_genes} genes\n"
            f"{self.counts.nbytes / 1024 / 1024:.1f} MiB in memory"
        )


def load_counts_table(path: Path) -> Dataset:
    """Read a delimited counts table and return it as a Dataset.

    The first row must hold gene identifiers and the first column cell
    identifiers; the leading corner cell is ignored. Values become float32.
    Suitable for small exported tables: the whole file is read into memory as a
    dense array, so a sparse matrix of many thousands of cells will not fit.

    Raises DatasetError for an unsupported extension, an empty or ragged table,
    duplicate labels, or values that are not finite non-negative numbers.
    Unreadable files raise OSError.
    """
    delimiter = _DELIMITERS.get(path.suffix.lower())
    if delimiter is None:
        raise DatasetError(
            f"Unsupported file type '{path.suffix}'. Use a .csv, .tsv, or .txt table."
        )

    # newline="" lets the csv module handle line endings inside quoted fields.
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.reader(handle, delimiter=delimiter) if row]

    if len(rows) < 2:
        raise DatasetError("The table needs a header row of genes and at least one cell.")

    gene_ids = tuple(name.strip() for name in rows[0][1:])
    if not gene_ids:
        raise DatasetError("The header row lists no genes after the first column.")
    _reject_duplicates(gene_ids, "gene")

    cell_ids: list[str] = []
    values = np.empty((len(rows) - 1, len(gene_ids)), dtype=np.float32)
    for index, row in enumerate(rows[1:]):
        # A ragged row means the file is damaged; a silent pad would invent data.
        if len(row) != len(gene_ids) + 1:
            raise DatasetError(
                f"Row {index + 2} has {len(row) - 1} values but the header lists "
                f"{len(gene_ids)} genes."
            )
        cell_ids.append(row[0].strip())
        try:
            values[index] = np.asarray(row[1:], dtype=np.float32)
        except ValueError as error:
            raise DatasetError(f"Row {index + 2} contains a non-numeric value.") from error

    _reject_duplicates(tuple(cell_ids), "cell")
    # Counts are abundances: a negative or missing entry is a file error, not data.
    if not np.isfinite(values).all():
        raise DatasetError("The table contains a missing or infinite value.")
    if (values < 0).any():
        raise DatasetError("The table contains a negative count.")

    logging.getLogger(__name__).info(
        "Loaded %d cells × %d genes from %s", len(cell_ids), len(gene_ids), path
    )
    return Dataset(values, tuple(cell_ids), gene_ids, path)


def _reject_duplicates(labels: tuple[str, ...], kind: str) -> None:
    """Raise DatasetError if a label is blank or repeated; otherwise return None."""
    if any(not label for label in labels):
        raise DatasetError(f"Every {kind} needs a non-empty identifier.")
    seen: set[str] = set()
    for label in labels:
        if label in seen:
            raise DatasetError(f"Duplicate {kind} identifier '{label}'.")
        seen.add(label)
