from fastapi import FastAPI


from enum import Enum
from typing import (
    Any,
    Awaitable,
    Callable,
    Coroutine,
    Dict,
    List,
    Optional,
    Sequence,
    Type,
    Union,
)

from fastapi import routing
from fastapi.datastructures import Default, DefaultPlaceholder
from fastapi.encoders import DictIntStrAny, SetIntStr
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.logger import logger
from fastapi.middleware.asyncexitstack import AsyncExitStackMiddleware
from fastapi.openapi.docs import (
    get_redoc_html,
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.openapi.utils import get_openapi
from fastapi.params import Depends
from fastapi.types import DecoratedCallable
from fastapi.utils import generate_unique_id
from starlette.applications import Starlette
from starlette.datastructures import State
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.errors import ServerErrorMiddleware
from starlette.middleware.exceptions import ExceptionMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import BaseRoute
from starlette.types import ASGIApp, Receive, Scope, Send


class CoreApp(FastAPI):
    def build_middleware_stack(self) -> ASGIApp:
        # Duplicate/override from Starlette to add AsyncExitStackMiddleware
        # inside of ExceptionMiddleware, inside of custom user middlewares
        debug = self.debug
        error_handler = None
        exception_handlers = {}

        for key, value in self.exception_handlers.items():
            if key in (500, Exception):
                error_handler = value
            else:
                exception_handlers[key] = value

        middleware = [
            Middleware(
            ServerErrorMiddleware, handler=error_handler, debug=debug
            ),
            Middleware(
                ExceptionMiddleware,
                handlers=exception_handlers,
                debug=debug
            ),
            *self.user_middleware,
            Middleware(AsyncExitStackMiddleware)
        ]

        app = self.router
        for cls, options in reversed(middleware):
            app = cls(app=app, **options)
        return app
