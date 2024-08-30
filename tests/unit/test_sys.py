import asyncio

from ryz.core import Code
from ryz.core import Ok, Res
from ryz.uuid import uuid4
from orwynn.yon.server import Bus, PubOpts, ok

from orwynn import (
    App,
    AppCfg,
    Plugin,
    SysInp,
    SysSpec,
)
from orwynn._pepel import AsyncPipeline
from tests.conftest import Mock_1, MockCfg, MockCon


async def test_main(app_cfg: AppCfg):
    async def sys_mock(inp: SysInp[Mock_1, MockCfg]) -> Res[None]:
        assert inp.msg.key == "hello"
        return Ok()

    plugin = Plugin(
        name="test",
        cfgtype=MockCfg,
        sys=[SysSpec(Mock_1, sys_mock)]
    )
    app_cfg.plugins.append(plugin)
    await App().init(app_cfg)

    r = (await Bus.ie().pubr(
        Mock_1(key="hello"), PubOpts(pubr_timeout=1))).unwrap()
    assert isinstance(r, ok)
