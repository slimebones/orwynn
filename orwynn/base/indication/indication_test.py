from typing import Any

from pytest import fixture

from orwynn.base.indication.Indication import Indication
from orwynn.base.indication.Indicator import Indicator
from orwynn.util.parsing.parsing import parse_key
from tests.std.text import Text


@fixture
def default_indication() -> Indication:
    mp: dict[str, Indicator] = {
        "type": Indicator.TYPE,
        "value": Indicator.VALUE
    }
    return Indication("Default", mp)


def test_digest_default(default_indication: Indication):
    digested_mp: dict[str, Any] = default_indication.digest(
        Text(text="hello")
    )

    mp_type: str = parse_key("type", digested_mp, str)
    mp_value: dict = parse_key("value", digested_mp, dict)

    assert mp_type == "Text"
    Text.parse_obj(mp_value)


def test_recover_default(default_indication: Indication):
    recovering_mp: dict[str, Any] = {
        "type": "Text",
        "value": {
            "text": "hello"
        }
    }

    recovered_model = default_indication.recover(recovering_mp)
    assert type(recovered_model) is Text
    assert recovered_model.text == "hello"
