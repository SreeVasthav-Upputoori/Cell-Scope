"""Annotated single-cell count matrices and importers for common formats."""

from dataclasses import dataclass, field
import csv
import gzip
import logging
from pathlib import Path
from typing import Any

import anndata as ad
import numpy as np
from scipy import sparse


_DELIMITERS = {".csv": ",", ".tsv": "\t", ".txt": "\t"}


class DatasetError(Exception):
    """Report malformed or unsupported data in words suitable for the UI."""


@dataclass(frozen=True, init=False)
class Dataset:
    """An annotated count matrix with an immutable active-cell selection.

    ``_adata.X`` holds the original count matrix, which may be dense or sparse.
    Filtering returns a new Dataset view with a smaller active selection while
    retaining the original matrix and all cell and gene metadata. Keep ``X``
    unchanged; future transforms belong in AnnData layers.

    The positional constructor remains compatible with small dense datasets:
    ``Dataset(counts, cell_ids, gene_ids, source)``. Use ``from_anndata`` for
    data read from `.h5ad` or 10x Matrix Market files.
    """

    _adata: ad.AnnData = field(repr=False, compare=False)
    source: Path
    _cell_mask: np.ndarray = field(repr=False, compare=False)

    def __init__(
        self,
        counts: Any,
        cell_ids: tuple[str, ...],
        gene_ids: tuple[str, ...],
        source: Path,
        cell_metadata: Any = None,
        gene_metadata: Any = None,
    ) -> None:
        cell_ids = tuple(str(value) for value in cell_ids)
        gene_ids = tuple(str(value) for value in gene_ids)
        _reject_duplicates(cell_ids, "cell")
        _reject_duplicates(gene_ids, "gene")
        if getattr(counts, "ndim", None) != 2 or counts.shape != (
            len(cell_ids), len(gene_ids)
        ):
            raise DatasetError("The count matrix shape does not match its cell and gene labels.")
        _validate_counts(counts)
        matrix = counts.tocsr() if sparse.issparse(counts) else np.asarray(counts)
        matrix = matrix.astype(np.float32, copy=False)
        try:
            annotated = ad.AnnData(
                X=matrix,
                obs=cell_metadata,
                var=gene_metadata,
            )
            annotated.obs_names = cell_ids
            annotated.var_names = gene_ids
        except (TypeError, ValueError) as error:
            raise DatasetError(f"Could not attach cell or gene metadata: {error}") from error
        self._set_state(annotated, Path(source), np.ones(len(cell_ids), dtype=bool))

    def _set_state(
        self, annotated: ad.AnnData, source: Path, cell_mask: np.ndarray
    ) -> None:
        object.__setattr__(self, "_adata", annotated)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "_cell_mask", cell_mask)

    @classmethod
    def from_anndata(cls, annotated: ad.AnnData, source: Path) -> "Dataset":
        """Wrap an AnnData matrix while retaining its annotations and layers."""
        if annotated.n_obs == 0 or annotated.n_vars == 0:
            raise DatasetError("The dataset must contain at least one cell and one gene.")
        cell_ids = tuple(str(value) for value in annotated.obs_names)
        gene_ids = tuple(str(value) for value in annotated.var_names)
        _reject_duplicates(cell_ids, "cell")
        _reject_duplicates(gene_ids, "gene")
        try:
            _validate_counts(annotated.X)
        except (TypeError, ValueError) as error:
            raise DatasetError(f"The AnnData object does not contain valid counts: {error}") from error
        result = cls.__new__(cls)
        result._set_state(annotated, Path(source), np.ones(annotated.n_obs, dtype=bool))
        return result

    @property
    def adata(self) -> ad.AnnData:
        """Return the active AnnData view with observation and gene metadata."""
        if self.n_cells == self._adata.n_obs:
            return self._adata
        return self._adata[self._cell_mask, :]

    @property
    def counts(self) -> Any:
        """Return active raw counts as a dense or sparse matrix."""
        if self.n_cells == self._adata.n_obs:
            return self._adata.X
        return self._adata.X[self._cell_mask]

    @property
    def raw_counts(self) -> Any:
        """Return the original, unfiltered raw counts matrix."""
        return self._adata.X

    @property
    def cell_ids(self) -> tuple[str, ...]:
        """Return identifiers for the currently selected cells."""
        return tuple(str(value) for value in self._adata.obs_names[self._cell_mask])

    @property
    def gene_ids(self) -> tuple[str, ...]:
        """Return gene identifiers in matrix column order."""
        return tuple(str(value) for value in self._adata.var_names)

    @property
    def cell_metadata(self):
        """Return metadata rows for the currently selected cells."""
        return self._adata.obs.iloc[np.flatnonzero(self._cell_mask)].copy()

    @property
    def gene_metadata(self):
        """Return metadata rows for all genes."""
        return self._adata.var.copy()

    @property
    def n_cells(self) -> int:
        """Return the number of active cells."""
        return int(self._cell_mask.sum())

    @property
    def n_genes(self) -> int:
        """Return the number of genes."""
        return self._adata.n_vars

    def with_cell_selection(self, keep: np.ndarray) -> "Dataset":
        """Return a new filtered view; the full raw matrix remains available."""
        keep = np.asarray(keep, dtype=bool)
        if keep.shape != (self.n_cells,):
            raise ValueError("Cell selection must have one value per active cell.")
        if not keep.any():
            raise ValueError("At least one cell must remain selected.")
        selection = self._cell_mask.copy()
        selection[np.flatnonzero(self._cell_mask)] = keep
        result = self.__class__.__new__(self.__class__)
        result._set_state(self._adata, self.source, selection)
        return result

    def summary(self) -> str:
        """Return a short description with dimensions and matrix memory use."""
        size = _matrix_nbytes(self._adata.X)
        display_size = f"{size} bytes"
        for exponent, unit in enumerate(("KiB", "MiB", "GiB"), start=1):
            scaled = size / 1024**exponent
            if scaled >= 1:
                display_size = f"{scaled:.1f} {unit}"
        return (
            f"{self.source.name}\n"
            f"{self.n_cells} cells × {self.n_genes} genes\n"
            f"{display_size} in memory"
        )


def load_counts_table(path: Path) -> Dataset:
    """Read a CSV/TSV/TXT table with cell rows and gene columns."""
    delimiter = _DELIMITERS.get(path.suffix.lower())
    if delimiter is None:
        raise DatasetError(
            f"Unsupported file type '{path.suffix}'. Use a .csv, .tsv, or .txt table."
        )

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
    _validate_counts(values)
    dataset = Dataset(values, tuple(cell_ids), gene_ids, path)
    logging.getLogger(__name__).info(
        "Loaded %d cells × %d genes from %s", dataset.n_cells, dataset.n_genes, path
    )
    return dataset


def load_h5ad(path: Path) -> Dataset:
    """Read an AnnData `.h5ad` file, preferring its `counts` layer when present.

    Files without a `counts` layer are interpreted as having raw counts in X.
    The imported matrix must be finite and non-negative. All AnnData annotations
    and other layers are retained.
    """
    try:
        annotated = ad.read_h5ad(path)
    except Exception as error:
        raise DatasetError(f"Could not read AnnData file: {error}") from error
    if "counts" in annotated.layers:
        annotated.X = annotated.layers["counts"]
        annotated.uns["cellscope_raw_counts_source"] = "layers/counts"
    else:
        annotated.uns["cellscope_raw_counts_source"] = "X"
    return Dataset.from_anndata(annotated, path)


def load_10x_mtx(path: Path) -> Dataset:
    """Read a 10x Matrix Market folder or one of its matrix.mtx files.

    Accepts compressed or uncompressed matrix, barcode, and feature files, and
    preserves feature IDs, names, types, and barcodes. 10x matrices are stored
    genes × cells, so they are transposed to CellScope's cells × genes layout.
    """
    folder = path if path.is_dir() else path.parent
    folder = _locate_10x_folder(folder)
    matrix_path = _find_companion(folder, ("matrix.mtx", "matrix.mtx.gz"))
    barcode_path = _find_companion(folder, ("barcodes.tsv", "barcodes.tsv.gz"))
    feature_path = _find_companion(
        folder,
        ("features.tsv", "features.tsv.gz", "genes.tsv", "genes.tsv.gz"),
    )
    barcodes = tuple(row[0].strip() for row in _read_tsv(barcode_path) if row)
    features = [row for row in _read_tsv(feature_path) if row]
    if not barcodes or not features:
        raise DatasetError("The 10x folder has no barcodes or gene features.")
    if any(len(row) < 2 for row in features):
        raise DatasetError("Each 10x feature row must include an ID and a name.")
    feature_ids = tuple(row[0].strip() for row in features)
    feature_names = tuple(row[1].strip() for row in features)
    feature_types = tuple(row[2].strip() if len(row) > 2 else "Gene Expression" for row in features)
    _reject_duplicates(barcodes, "cell")
    _reject_duplicates(feature_ids, "gene")
    if any(not name for name in feature_names):
        raise DatasetError("Every 10x feature needs a non-empty name.")

    try:
        feature_by_cell = ad.io.read_mtx(matrix_path, dtype="float32").X
    except Exception as error:
        raise DatasetError(f"Could not read the 10x Matrix Market matrix: {error}") from error
    if feature_by_cell.shape != (len(feature_ids), len(barcodes)):
        raise DatasetError(
            "The 10x matrix dimensions do not match its feature and barcode files."
        )
    counts = sparse.csr_matrix(feature_by_cell.T, dtype=np.float32)
    _validate_counts(counts)
    annotated = ad.AnnData(X=counts)
    annotated.obs_names = barcodes
    annotated.var_names = feature_ids
    annotated.var["feature_name"] = feature_names
    annotated.var["feature_type"] = feature_types
    dataset = Dataset.from_anndata(annotated, path)
    logging.getLogger(__name__).info(
        "Loaded 10x matrix with %d cells × %d genes from %s",
        dataset.n_cells,
        dataset.n_genes,
        path,
    )
    return dataset


def load_dataset(path: Path) -> Dataset:
    """Load a delimited table, `.h5ad`, or 10x Matrix Market dataset."""
    if path.is_dir() or path.name.lower().startswith("matrix.mtx"):
        return load_10x_mtx(path)
    if path.suffix.lower() == ".h5ad":
        return load_h5ad(path)
    return load_counts_table(path)


def _validate_counts(counts: Any) -> None:
    """Reject non-finite or negative values without densifying sparse input."""
    values = counts.data if sparse.issparse(counts) else np.asarray(counts)
    if not np.isfinite(values).all():
        raise DatasetError("The count matrix contains a missing or infinite value.")
    if (values < 0).any():
        raise DatasetError("The count matrix contains a negative value.")


def _matrix_nbytes(matrix: Any) -> int:
    """Return dense bytes or the stored data/index bytes of a sparse matrix."""
    if sparse.issparse(matrix):
        return int(matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes)
    return int(np.asarray(matrix).nbytes)


def _locate_10x_folder(folder: Path) -> Path:
    """Resolve a sample folder or a standard filtered/raw feature subfolder."""
    candidates = (folder, folder / "filtered_feature_bc_matrix", folder / "raw_feature_bc_matrix")
    for candidate in candidates:
        if any((candidate / name).is_file() for name in ("matrix.mtx", "matrix.mtx.gz")):
            return candidate
    raise DatasetError(
        "Choose a 10x folder containing matrix.mtx, barcodes.tsv, and features.tsv."
    )


def _find_companion(folder: Path, names: tuple[str, ...]) -> Path:
    """Return a required 10x file, or explain which companion is missing."""
    for name in names:
        candidate = folder / name
        if candidate.is_file():
            return candidate
    raise DatasetError(f"The 10x folder is missing {names[0]}.")


def _read_tsv(path: Path) -> list[list[str]]:
    """Read a possibly gzipped tab-separated 10x metadata file."""
    opener = gzip.open if path.suffix.lower() == ".gz" else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as handle:
        return list(csv.reader(handle, delimiter="\t"))


def _reject_duplicates(labels: tuple[str, ...], kind: str) -> None:
    """Raise DatasetError if a label is blank or repeated."""
    if any(not label for label in labels):
        raise DatasetError(f"Every {kind} needs a non-empty identifier.")
    seen: set[str] = set()
    for label in labels:
        if label in seen:
            raise DatasetError(f"Duplicate {kind} identifier '{label}'.")
        seen.add(label)
