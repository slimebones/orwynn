from orwynn.base.module.module import Module
from orwynn.boot.boot import Boot
from orwynn.http.controller.controller import HttpController
from orwynn.http.controller.endpoint.endpoint import Endpoint
from orwynn.testing.client import Client


def test_basic():
    class C1(HttpController):
        ROUTE = "/"
        ENDPOINTS = [Endpoint(method="get")]

        def get(self):
            return {}

    boot: Boot = Boot(
        Module(route="/", Controllers=[C1]),
        apprc={
            "prod": {
                "App": {
                    "cors": {
                        "is_enabled": True,
                        "allow_origins": ["*"]
                    }
                }
            }
        }
    )
    http: Client = boot.app.client

    r = http.options(
        "/",
        headers={
            "origin": "hello",
            "access-control-request-method": "GET"
        }
    )

    assert r.headers.get("access-control-allow-origin") == "*"


def test_correct_origin():
    class C1(HttpController):
        ROUTE = "/"
        ENDPOINTS = [Endpoint(method="get")]

        def get(self) -> dict:
            return {}

    boot: Boot = Boot(
        Module(route="/", Controllers=[C1]),
        apprc={
            "prod": {
                "App": {
                    "cors": {
                        "is_enabled": True,
                        "allow_origins": ["hello"]
                    }
                }
            }
        }
    )
    http: Client = boot.app.client


    r = http.options(
        "/",
        headers={
            "origin": "hello",
            "access-control-request-method": "POST"
        }
    )

    assert r.headers.get("access-control-allow-origin") == "hello"


def test_wrong_origin():
    class C1(HttpController):
        ROUTE = "/"
        ENDPOINTS = [Endpoint(method="get")]

    boot: Boot = Boot(
        Module(route="/", Controllers=[C1]),
        apprc={
            "prod": {
                "App": {
                    "cors": {
                        "is_enabled": True,
                        "allow_origins": ["nothello"]
                    }
                }
            }
        }
    )
    http: Client = boot.app.client

    r = http.options(
        "/",
        headers={
            "origin": "hello",
            "access-control-request-method": "POST"
        }
    )

    assert r.headers.get("access-control-allow-origin") is None


def test_unsuccessful():
    """
    Unsuccessful responses should also contain according CORS headers.
    """
    class C1(HttpController):
        ROUTE = "/"
        ENDPOINTS = [Endpoint(method="get")]

        def get(self):
            raise ValueError("cors test")

    boot: Boot = Boot(
        Module(route="/", Controllers=[C1]),
        apprc={
            "prod": {
                "App": {
                    "cors": {
                        "is_enabled": True,
                        "allow_origins": ["*"]
                    }
                }
            }
        }
    )
    http: Client = boot.app.client

    r = http.options(
        "/",
        headers={
            "origin": "hello",
            "access-control-request-method": "GET"
        }
    )
    assert r.headers.get("access-control-allow-origin") == "*"

    r = http.get(
        "/",
        headers={
            "origin": "hello"
        }
    )
    assert r.json()["type"] == "error"
    assert r.headers.get("access-control-allow-origin") == "*"
