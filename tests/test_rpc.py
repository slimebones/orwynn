import asyncio

from pykit.code import Code
from pykit.res import Ok
from pykit.uuid import uuid4
from rxcat import SrpcSend

from orwynn import App, AppCfg, SysArgs, rsys
from tests.conftest import Mock_1, MockCfg, MockConn


async def test_main(app_cfg: AppCfg):
    @rsys(MockCfg)
    async def rsys__mock(args: SysArgs[MockCfg], body: Mock_1):
        assert body.key == "hello"
        assert args.cfg.num == 1
        return Ok(152)

    app = await App().init(app_cfg)
    bus = app.get_bus().eject()
    conn = MockConn()
    conn_task = asyncio.create_task(bus.conn(conn))

    rpckey = "mock::" + uuid4()
    await conn.client__send({
        "sid": uuid4(),
        "bodycodeid": (await Code.get_regd_codeid_by_type(SrpcSend)).eject(),
        "body": {
            "key": rpckey,
            "body": {
                "key": "hello"
            }
        }
    })
    # welcome
    await asyncio.wait_for(conn.client__recv(), 1)
    r = await asyncio.wait_for(conn.client__recv(), 1)
    body = r["body"]
    assert body["key"] == rpckey
    assert body["val"] == 152

    conn_task.cancel()
