"""Check matrix reading, label validation, and rejection of malformed tables."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np

from cellscope.dataset import Dataset, DatasetError, load_counts_table


class DatasetTest(unittest.TestCase):
    """Read tables from temporary files so no research data is required."""

    def setUp(self) -> None:
        """Allocate a temporary directory removed after each test."""
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def write(self, name: str, text: str) -> Path:
        """Create a table file and return its path."""
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_reads_cells_as_rows(self) -> None:
        """A valid table becomes a float32 matrix with its labels in order."""
        path = self.write("counts.csv", "cell,GeneA,GeneB\nc1,1,2\nc2,3,4.5\n")
        dataset = load_counts_table(path)
        self.assertEqual(dataset.cell_ids, ("c1", "c2"))
        self.assertEqual(dataset.gene_ids, ("GeneA", "GeneB"))
        self.assertEqual((dataset.n_cells, dataset.n_genes), (2, 2))
        self.assertEqual(dataset.counts.dtype, np.float32)
        self.assertTrue(np.allclose(dataset.counts, [[1, 2], [3, 4.5]]))

    def test_reads_tab_separated_table(self) -> None:
        """A .tsv file is split on tabs rather than commas."""
        dataset = load_counts_table(self.write("counts.tsv", "cell\tGeneA\nc1\t7\n"))
        self.assertEqual(dataset.gene_ids, ("GeneA",))
        self.assertEqual(dataset.counts[0][0], 7)

    def test_summary_reports_dimensions(self) -> None:
        """The display summary names the file and its cell and gene totals."""
        dataset = load_counts_table(self.write("counts.csv", "cell,GeneA\nc1,1\n"))
        summary = dataset.summary()
        self.assertIn("counts.csv", summary)
        self.assertIn("1 cells × 1 genes", summary)

    def test_rejects_unsupported_extension(self) -> None:
        """An unknown extension is refused instead of parsed by guesswork."""
        with self.assertRaises(DatasetError):
            load_counts_table(self.write("counts.h5ad", "cell,GeneA\nc1,1\n"))

    def test_rejects_header_only_table(self) -> None:
        """A file without data rows cannot describe any cell."""
        with self.assertRaises(DatasetError):
            load_counts_table(self.write("counts.csv", "cell,GeneA,GeneB\n"))

    def test_rejects_ragged_row(self) -> None:
        """A row whose width differs from the header names the offending line."""
        path = self.write("counts.csv", "cell,GeneA,GeneB\nc1,1,2\nc2,3\n")
        with self.assertRaises(DatasetError) as caught:
            load_counts_table(path)
        self.assertIn("Row 3", str(caught.exception))

    def test_rejects_non_numeric_value(self) -> None:
        """Text in a count column is an error rather than a zero."""
        with self.assertRaises(DatasetError):
            load_counts_table(self.write("counts.csv", "cell,GeneA\nc1,high\n"))

    def test_rejects_negative_and_missing_values(self) -> None:
        """Counts are abundances, so negative or absent numbers are refused."""
        with self.assertRaises(DatasetError):
            load_counts_table(self.write("neg.csv", "cell,GeneA\nc1,-1\n"))
        with self.assertRaises(DatasetError):
            load_counts_table(self.write("nan.csv", "cell,GeneA\nc1,nan\n"))

    def test_rejects_duplicate_and_blank_labels(self) -> None:
        """Repeated or empty identifiers would make rows indistinguishable."""
        with self.assertRaises(DatasetError):
            load_counts_table(self.write("gene.csv", "cell,GeneA,GeneA\nc1,1,2\n"))
        with self.assertRaises(DatasetError):
            load_counts_table(self.write("cell.csv", "cell,GeneA\nc1,1\nc1,2\n"))
        with self.assertRaises(DatasetError):
            load_counts_table(self.write("blank.csv", "cell,GeneA\n,1\n"))

    def test_missing_file_raises_oserror(self) -> None:
        """A file system problem stays an OSError for the caller to report."""
        with self.assertRaises(OSError):
            load_counts_table(self.root / "absent.csv")

    def test_dataset_labels_are_immutable(self) -> None:
        """The frozen dataclass prevents a page from editing a loaded dataset."""
        dataset = Dataset(np.zeros((1, 1), dtype=np.float32), ("c1",), ("g1",), Path("x"))
        with self.assertRaises(Exception):
            dataset.cell_ids = ("c2",)


if __name__ == "__main__":
    unittest.main()
