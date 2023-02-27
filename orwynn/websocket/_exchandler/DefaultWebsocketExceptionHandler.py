from orwynn.base.exchandler._ExceptionHandler import ExceptionHandler
from orwynn.proxy._BootProxy import BootProxy
from orwynn.websocket import Websocket


class DefaultWebsocketExceptionHandler(ExceptionHandler):
    E = Exception

    async def handle(
        self, request: Websocket, error: Exception
    ) -> None:
        await request.send_json(BootProxy.ie().api_indication.digest(
            error
        ))
