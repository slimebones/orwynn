
from orwynn.indication.Indicatable import Indicatable
from orwynn.model.Model import Model


class EndpointResponse(Model):
    status_code: int
    Entity: type[Indicatable]
    description: str | None = None
