from orwynn.indication.indication import Indication
from orwynn.indication.indicator import Indicator

default_api_indication: Indication = Indication(
    {
        "type": Indicator.Type,
        "value": Indicator.Value
    }
)
