from orwynn import web
from orwynn.log.Log import Log
from orwynn.web.context.RequestContextId import RequestContextId
from orwynn.error.Error import Error
from orwynn.log.HTTPLogger import HTTPLogger
from orwynn.middleware.Middleware import Middleware, NextCallFn


class LogMiddleware(Middleware):
    """Logs information about request and response lihking them together.

    It's recommended to be outermost (at custom level) middleware.
    """
    def __init__(self, covered_routes: list[str], log: Log) -> None:
        super().__init__(covered_routes)

        self.__http_logger: HTTPLogger = HTTPLogger(log)

    async def process(
        self, request: web.Request, call_next: NextCallFn
    ) -> web.Response:
        request_id: str = RequestContextId().get()
        await self.__http_logger.log_request(
            request,
            request_id
        )

        response: web.Response = await call_next(request)

        await self.__http_logger.log_response(
            response,
            request=request,
            request_id=request_id
        )

        return response
