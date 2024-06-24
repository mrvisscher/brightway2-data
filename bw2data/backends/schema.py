from peewee import DoesNotExist, Model, TextField, FloatField, IntegerField

from ..errors import UnknownObject
from ..sqlite import PickleField

ids = []


def create_unique_id():
    if not ids:
        [ids.append(x.id) for x in ActivityDataset.select(ActivityDataset.id)]
        [ids.append(x.id) for x in ProductDataset.select(ProductDataset.id)]
        ids.sort()
    if not ids:
        return 0
    ids.append(ids[-1] + 1)
    return ids[-1]


class ActivityDataset(Model):
    matrix_id = IntegerField(default=create_unique_id)
    data = PickleField()  # Canonical, except for other C fields
    code = TextField()  # Canonical
    database = TextField()  # Canonical
    location = TextField(null=True)  # Reset from `data`
    name = TextField(null=True)  # Reset from `data`
    product = TextField(null=True)  # Reset from `data`
    type = TextField(null=True)  # Reset from `data`

    @property
    def key(self):
        return (self.database, self.code)


class ProductDataset(Model):
    """
    - Make products uniquely identifiable within an activity
    - Create a field for the allocation factor that has a default value of 1

    """
    matrix_id = IntegerField(default=create_unique_id)
    data = PickleField()  # Canonical, except for other C fields
    code = TextField()
    source_code = TextField()  # Canonical
    database = TextField()  # Canonical
    name = TextField(null=True)  # Reset from `data`
    allocation = FloatField(default=1.0)
    alloc_total = FloatField(default=1.0)
    type = TextField()  # Reset from `data`


class ExchangeDataset(Model):
    data = PickleField()  # Canonical, except for other C fields
    input_code = TextField()  # Canonical
    input_database = TextField()  # Canonical
    output_code = TextField()  # Canonical
    output_database = TextField()  # Canonical
    type = TextField()  # Reset from `data`


def get_id(key):
    if isinstance(key, int):
        return key
    else:
        try:
            return ActivityDataset.get(
                ActivityDataset.database == key[0], ActivityDataset.code == key[1]
            ).matrix_id
        except DoesNotExist:
            raise UnknownObject
