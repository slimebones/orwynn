from orwynn import app
from orwynn.base.controller.Controller import Controller
from orwynn.base.middleware._Middleware import Middleware
from orwynn.di.BUILTIN_PROVIDERS import BUILTIN_PROVIDERS
from orwynn.di.acceptor import Acceptor


"""List of builtin classes are able to accept Providers.
"""
BUILTIN_ACCEPTORS: list[type[Acceptor]] = [
    # All Providers are Acceptors at the same time
    *BUILTIN_PROVIDERS,
    Controller,
    Middleware,
    app.ErrorHandler
]
