from . import databases, config
from .backends.single_file import SingleFileDatabase
from .backends.json import JSONDatabase
from .backends.blitz import BlitzLCIDatabase


def DatabaseChooser(name, backend=None):
    """A method that returns a database class instance. The default database type is `SingleFileDatabase`. `JSONDatabase` stores each process dataset in indented JSON in a separate file. Database types are specified in `databases[database_name]['backend']`.

    New database types can be registered with the config object:

    .. code-block:: python

        config.backends['backend type string'] = MyNewBackendClass

    .. warning:: Registering new backends must be done each time you start the Python interpreter.

    To test whether an object is a database subclass, do:

    .. code-block:: python

        from bw2data.backends import LCIBackend
        isinstance(my_database, LCIBackend)

    """
    if name in databases:
        backend = databases[name].get(u"backend", backend or u"blitz")
    else:
        backend = backend or u"blitz"

    # Backwards compatibility
    if backend == u"default":
        databases[name][u'backend'] = u'singlefile'
        databases.flush()
        return SingleFileDatabase(name)
    elif backend == u"blitz":
        return BlitzLCIDatabase(name)
    elif backend == u"singlefile":
        return SingleFileDatabase(name)
    elif backend == u"json":
        return JSONDatabase(name)
    elif backend in config.backends:
        return config.backends[backend](name)
    else:
        raise ValueError(u"Backend {} not found".format(backend))


# Backwards compatibility
Database = DatabaseChooser
