# -*- coding: utf-8 -*
from .. import Database, databases
from ..logs import get_io_logger
from ..utils import activity_hash
from ..units import normalize_units
import csv
import itertools
import os
import pprint
import re
import warnings

# Pattern for SimaPro munging of ecoinvent names
detoxify_pattern = '/(?P<geo>[A-Z]{2,10})(/I)? [SU]$'
detoxify_re = re.compile(detoxify_pattern)


class MissingExchange(StandardError):
    """Exchange can't be matched"""
    pass


def detoxify(string, log):
    found = detoxify_re.findall(string)
    if not found:
        log.warning(u"Name '%s' doesn't have SimaPro slashes™ - matched without slashes" % string)
        return [string, False]

    geo = found[0][0]
    name = re.sub(detoxify_pattern, '', string)
    return [name, geo]


def is_number(x):
    try:
        float(x)
        return True
    except:
        return False

INTRODUCTION = """Starting SimaPro import:
\tFilepath: %s
\tDelimiter: %s
\tDepends: %s
\tName: %s
\tDefault geo: %s
"""

SIMAPRO_BIOSPHERE = set(["Resources", "Emissions to air", "Emissions to water", "Emissions to soil"])


class SimaProImporter(object):
    """Import a SimaPro text-delimited (CSV) file into a new database.

    `SimaPro <http://www.pre-sustainability.com/simapro-lca-software>`_ is a leading commercial LCA software made by `Pré sustainbility <http://www.pre-sustainability.com/>`_.

    .. warning:: Only import of text-delimited files is supported.

    The SimaPro export must be done with exactly the following options checked:

    .. image:: images/simapro-options.png
        :align: center

    The basic logic of the SimaPro importer is as follows:

    .. image:: images/import-simapro.png
        :align: center

    The SimaPro importer has solid basic functionality:
        * SimaPro names are detoxified back to ecoinvent standards
        * Links to background databases like ecoinvent can be included

    However, the SimaPro importer has the following limitations:
        * Multioutput datasets are not supported
        * Linking against datasets other than ecoinvent is not tested (most are not available otherwise)
        * Modifying an existing database is not supported; it can only be overwritten completely.
        * Uncertainty data is not imported.
        * Biosphere flows are not imported.
        * Not all SimaPro unit changes from ecoinvent are included (no comprehensive list seems to be available)

    **Instantiation**

    Global variables:
        * ``self.db_name``: str
        * ``self.default_geo``: str
        * ``self.delimiter``: character
        * ``self.depends``: list
        * ``self.filepath``: str
        * ``self.log``: file object
        * ``self.logfile``: str
        * ``self.overwrite``: bool

    Args:
        * ``filepath``: Filepath for file to important.
        * ``delimiter`` (str, default=tab character): Delimiter character for CSV file.
        * ``depends`` (list, default= ``['ecoinvent 2.2']`` ): List of databases referenced by datasets in this file.
        * ``overwrite`` (bool, default=False): Overwrite existing database.
        * ``name`` (str, default=None): Name of the database to import. If not specified, the SimaPro project name will be used.
        * ``default_geo`` (str, default= ``GLO`` ): Default location for datasets with no location is specified.

    """
    def __init__(self, filepath, delimiter="\t", depends=['ecoinvent 2.2'],
                 overwrite=False, name=None, default_geo="GLO"):
        assert os.path.exists(filepath), "Can't find file %s" % filepath
        self.filepath = filepath
        self.delimiter = delimiter
        self.depends = depends
        self.overwrite = overwrite
        self.db_name = name
        self.default_geo = default_geo
        self.log, self.logfile = get_io_logger("SimaPro importer")

    def importer(self):
        """Import the SimaPro file."""
        self.log.info(INTRODUCTION % (
            self.filepath,
            self.delimiter,
            ", ".join(self.depends),
            self.db_name,
            self.default_geo
        ))
        data = self.load_file()
        self.verify_simapro_file(data)
        format = data[0][0]
        data = self.clean_data(data)
        self.log.info("Found %s datasets" % len(data))
        data = [self.process_data(obj) for obj in data]
        self.create_foreground(data)
        self.load_background()
        data = [self.link_exchanges(obj) for obj in data]
        if not self.overwrite:
            assert self.db_name not in databases, (
                "Already imported this project\n"
                "Delete existing database, give new name, or use ``overwrite``."
            )
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                database = Database(self.db_name)
                database.register(
                    format=format,
                    depends=self.depends,
                    num_processes=len(data)
                )
        else:
            if self.db_name in databases:
                self.warning("Overwriting database %s" % self.db_name)
            database = Database(self.db_name)
        database.write(dict([(obj['code'], obj) for obj in data]))
        database.process()
        return self.db_name, self.logile

    def load_file(self):
        """Open the CSV file and load the data.

        Returns:
            The loaded data: a list of lists.

        """
        return [x for x in csv.reader(
            open(self.filepath),
            delimiter=self.delimiter
        )]

    def verify_simapro_file(self, data):
        """Check to make sure file is valid SimaPro export.

        Args:
            *data*: The raw data loaded from the CSV file.

        """
        assert 'SimaPro' in data[0][0], "File is not valid SimaPro export"

    def clean_data(self, data):
        """Clean the raw data.

        1. Set the database name, if not already specified.
        2. Split datasets.

        Args:
            * *data*: The raw data loaded from the CSV file.

        Returns:
            Cleaned data.

        """
        if self.db_name is None:
            assert data[1][0] == 'Project', "Can't determine SimaPro project name"
            self.db_name = data[1][1]
        process_indices = self.get_process_indices(data)
        process_data = [
            data[process_indices[x]:process_indices[x + 1]]
            for x in range(len(process_indices) - 1)
        ]
        return process_data

    def get_process_indices(self, data):
        """Get CSV row indices for the start of each new activity dataset.

        Args:
            *data*: The CSV list of lists

        Returns:
            List of row index numbers

        """
        return [x for x in range(2, len(data))
            if data[x] and data[x][0] == "Process" and len(data[x]) == 1
            ] + [len(data) + 1]

    def process_data(self, dataset):
        """Transform the raw dataset data to a more structured format.

        1. Add metadata like name, unit, etc.
        2. Create a list of exchanges, including the production exchange.

        Args:
            *dataset*: The raw activity dataset.

        Returns:
            Structured dataset.

        """
        data = self.define_dataset(dataset)
        data['simapro metadata'] = self.get_dataset_metadata(dataset)
        data['exchanges'] = self.get_exchanges(dataset)
        data['exchanges'].append(self.get_production_exchange(data, dataset))
        return data

    def define_dataset(self, dataset):
        """Use the first *Products* line to define the dataset.

        Unfortunately, all SimaPro metadata is unreliable, and can't be used.

        Args:
            *dataset*: The activity dataset.

        Returns:
            A dictionary of normal Brightway2 activity data.

        """
        line = dataset[self.get_exchanges_index(dataset) + 1]
        name, geo = detoxify(line[0], self.log)
        data = {
            'name': name,
            'unit': normalize_units(line[2]),
            'location': geo or self.default_geo,
            'categories': line[5].split('\\')
        }
        data['code'] = (self.db_name, activity_hash(data))
        return data

    def get_dataset_metadata(self, dataset):
        """Get SimaPro-defined metadata about the dataset.

        Args:
            *dataset*: The activity dataset.

        Returns:
            A dictionary of metadata.

        """
        metadata = {}
        for index, line in enumerate(dataset):
            if line and line[0] == 'Products':
                break
            elif not bool(line and len(line) > 1 and line[0] and line[1]):
                continue
            elif dataset[index + 1] and not dataset[index + 1][0]:
                # Multi-line metadata; concatenate
                metadata[line[0]] = [line[1]] + [
                    x[1] for x in itertools.takewhile(
                    lambda y: y and not y[0], dataset[index + 1:])
                ]
            else:
                metadata[line[0]] = line[1]

        return metadata

    def get_exchanges(self, dataset):
        """Structure the list of exchanges.

        Args:
            *dataset*: The activity dataset.

        Returns:
            Structured list of exchanges.

        """
        exchanges = []
        x = self.get_exchanges_index(dataset)
        assert len(dataset[x + 2]) == 0, "Can't import multioutput datasets"

        for line in dataset[x + 3:]:
            if len(line) == 0:
                continue
            elif len(line) == 1:
                label = line[0]
            elif label in SIMAPRO_BIOSPHERE:
                continue
            else:
                # Try to interpret as ecoinvent
                name, geo = detoxify(line[0], self.log)
                exchanges.append({
                    'name': name,
                    'amount': float(line[1]),
                    'comment': label,
                    'unit': normalize_units(line[2]),
                    'uncertainty': line[3],
                    'location': geo
                })
        return exchanges

    def get_exchanges_index(self, dataset):
        """Get index for start of exchanges in activity dataset."""
        for x in range(len(dataset)):
            if dataset[x] and dataset[x][0] == 'Products':
                return x

    def get_production_exchange(self, data, dataset):
        """Get the production exchange"""
        line = dataset[self.get_exchanges_index(dataset) + 1]
        return {
            'amount': float(line[1]),
            'input': data['code'],
            'uncertainty type': 0,
            'type': 'production'
        }

    def create_foreground(self, data):
        """Create the set of foreground processes to match exchanges against.

        Global variables:
            * ``self.foreground``: dict

        Args:
            *data*: The structured activity datasets.

        """
        self.foreground = dict([
            ((ds['name'], ds['unit']), ds['code']) for ds in data
        ])

    def load_background(self):
        """Load the background data to match exchanges against.

        Need to be able to match against both ``(name, unit, geo)`` and ``(name, unit)``.

        Global variables:
            * ``self.background``: dict

        """
        background_data = {}
        for db in self.depends:
            background_data.update(**Database(db).load())

        self.background = {}
        for key, value in background_data.iteritems():
            self.background[(value['name'].lower(), value['unit'],
                            value['location'])] = key
            self.background[(value['name'].lower(), value['unit'])] = key

    def link_exchanges(self, dataset):
        """Link all exchanges in a given dataset"""
        dataset['exchanges'] = [
            self.link_exchange(exc) for exc in dataset['exchanges']
        ]
        return dataset

    def link_exchange(self, exc):
        """Try to link an exchange.

        This isn't easy, as SimaPro only gives us names and units, and often the names are incorrect.

        This method looks first in the foreground, then the background; if an exchange isn't found an error is rasied."""
        if exc.get('type', None) == 'production':
            return exc
        elif (exc["name"], exc["unit"]) in self.foreground:
            exc["input"] = self.foreground[(exc["name"], exc["unit"])]
            found = True
        elif (exc["name"].lower(), exc["unit"], exc['location']) in \
                self.background:
            exc["input"] = self.background[(exc["name"].lower(), exc["unit"],
                exc['location'])]
            found = True
        elif (exc["name"].lower(), exc["unit"], exc['location']) in \
                self.background:
            exc["input"] = self.background[(exc["name"].lower(), exc["unit"],
                exc['location'])]
            found = True
        else:
            found = False

        if found:
            exc["type"] = "technosphere"
            exc['uncertainty type'] = 0
            return exc
        else:
            raise MissingExchange(
                "Can't find exchange\n%s" % pprint.pformat(exc, indent=4)
            )