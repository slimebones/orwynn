"""Main framework-only testing suite.
"""
import contextlib
import os

from pytest import fixture

from orwynn._di.collecting.collect_modules_test import std_modules
from orwynn._di.collecting.collect_provider_dependencies_test import (
    std_provider_dependencies_map,
)
from orwynn._di.Di import Di
from orwynn._di.di_test import std_di_container
from orwynn._di.MissingDiObjectError import MissingDiObjectError
from orwynn.app import AppMode
from orwynn.app._App import App
from orwynn.app.app_test import std_app
from orwynn.base.module._Module import Module
from orwynn.base.worker._Worker import Worker
from orwynn.boot._Boot import Boot
from orwynn.boot.boot_test import (
    run_std,
    set_std_apprc_path_env,
    std_boot,
    std_mongo_boot,
)
from orwynn.helpers.ENVIRONS import ENVIRONS
from orwynn.http._controller.endpoint.endpoint_test import run_endpoint
from orwynn.http.testing import std_http
from orwynn.log.log_test import log_apprc_sink_to_writer, writer
from orwynn.mongo._Mongo import Mongo
from orwynn.testing._Client import Client
from orwynn.testing._EmbeddedTestClient import EmbeddedTestClient
from orwynn.utils import validation
from tests.structs import (
    circular_module_struct,
    long_circular_module_struct,
    self_importing_module_struct,
    std_struct,
)


@fixture(autouse=True)
def run_around_tests():
    os.environ["ORWYNN_MODE"] = "test"

    yield

    # Suppress:
    #   MissingDIObjectError: Mongo is not initialized, skip
    #   TypeError: DI wasn't initialized, skip
    with contextlib.suppress(MissingDiObjectError, TypeError):
        validation.apply(Di.ie().find("Mongo"), Mongo).drop_database()
    _discardWorkers()


def _discardWorkers(W: type[Worker] = Worker):
    for NestedW in W.__subclasses__():
        _discardWorkers(NestedW)
    W.discard(should_validate=False)

    _delete_environs()


def _delete_environs():
    for environ in ENVIRONS:
        with contextlib.suppress(KeyError):
            del os.environ[environ]
