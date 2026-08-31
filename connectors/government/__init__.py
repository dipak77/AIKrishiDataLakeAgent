"""Government of India source connectors (data.gov.in / OGD platform)."""

from .agmarknet import AgmarknetConnector
from .data_gov import DataGovConnector
from .imd import ImdConnector
from .kcc import KccConnector
from .soil_health import SoilHealthConnector

__all__ = [
    "DataGovConnector",
    "KccConnector",
    "AgmarknetConnector",
    "ImdConnector",
    "SoilHealthConnector",
]
