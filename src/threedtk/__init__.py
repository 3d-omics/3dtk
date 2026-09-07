"""3D'omics ToolKit.

Installed as the ``3dtk`` distribution; imported as ``threedtk`` because Python
identifiers cannot begin with a digit.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
import re

from threedtk.api import (
    CatalogError,
    ChecksumMismatchError,
    CountCell,
    CountsError,
    Cryosection,
    Database,
    DenseMatrix,
    Experiment,
    FetchPlan,
    FetchSummary,
    Genome,
    Macrosample,
    MatrixSource,
    Microsample,
    Specimen,
    StatBreakdown,
    TargetStats,
    UnfetchableRecord,
    UnsupportedSchemaVersionError,
    ValueCount,
    ValuesResult,
)
from threedtk.catalog import PINNED_CATALOG

__all__ = [
    "__version__",
    "CatalogError",
    "ChecksumMismatchError",
    "CountCell",
    "CountsError",
    "Cryosection",
    "Database",
    "DenseMatrix",
    "Experiment",
    "FetchPlan",
    "FetchSummary",
    "Genome",
    "Macrosample",
    "MatrixSource",
    "Microsample",
    "PINNED_CATALOG",
    "Specimen",
    "StatBreakdown",
    "TargetStats",
    "UnfetchableRecord",
    "UnsupportedSchemaVersionError",
    "ValueCount",
    "ValuesResult",
]


def _version_from_pyproject() -> str:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if not pyproject_path.exists():
        raise PackageNotFoundError("pyproject.toml not found")
    match = re.search(
        r'(?m)^version = "([^"]+)"$', pyproject_path.read_text(encoding="utf-8")
    )
    if not match:
        raise PackageNotFoundError("version not found in pyproject.toml")
    return match.group(1)


try:
    __version__ = _version_from_pyproject()
except PackageNotFoundError:
    __version__ = package_version("3dtk")
