import os

from .. import config
from ..project import projects
from ..sqlite import SubstitutableDatabase
from .schema import ActivityDataset, ExchangeDataset, ProductDataset, get_id

sqlite3_lci_db = SubstitutableDatabase(
    projects.dir / "lci" / "databases.db",
    [ActivityDataset, ProductDataset, ExchangeDataset],
)

from .base import SQLiteBackend
from .proxies import Activity, Exchange, Product
from .utils import convert_backend

config.sqlite3_databases.append(
    (
        os.path.join("lci", "databases.db"),
        sqlite3_lci_db,
    )
)

Node = Activity
Edge = Exchange
