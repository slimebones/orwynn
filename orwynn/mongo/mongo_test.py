from orwynn.base.mapping.CustomUseOfMappingReservedFieldError import \
    CustomUseOfMappingReservedFieldError
from orwynn.base.test.HttpClient import HttpClient
from orwynn.mongo.DuplicateKeyError import DuplicateKeyError
from orwynn.mongo._MongoMapping import MongoMapping
from orwynn.proxy.BootProxy import BootProxy
from orwynn.util import validation
from orwynn.util.web import TestResponse
from tests.std.user import User


def test_user_create(std_mongo_boot, std_http: HttpClient):
    r: TestResponse = std_http.post(
        "/users",
        200,
        json={
            "name": "Mark Watney"
        }
    )
    created_user: User = User.recover(r.json())
    User.find_one(id=created_user.id)


def test_reserved_mapping_field(std_mongo_boot, std_http: HttpClient):
    class M(MongoMapping):
        mongo_filter: int

    validation.expect(M, CustomUseOfMappingReservedFieldError, mongo_filter=1)


def test_same_id_creation(std_mongo_boot, std_http: HttpClient):
    r: TestResponse = std_http.post(
        "/users",
        200,
        json={
            "name": "Mark Watney"
        }
    )
    r2: TestResponse = std_http.post(
        "/users",
        400,
        json={
            "id": r.json()["value"]["id"],
            "name": "Mark Watney"
        }
    )

    validation.validate(
        BootProxy.ie().api_indication.recover(r2.json()),
        DuplicateKeyError
    )
