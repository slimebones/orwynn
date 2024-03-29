from orwynn.admin import handle_get_indexed_codes
from orwynn.boot import BootCfg, RouteSpec
from orwynn.mongo import MongoCfg
from orwynn.preload import PreloadCfg, handle_preload

default = {
    "test": [
        BootCfg(
            std_verbosity=2,
            route_specs=[
                RouteSpec(
                    method="post",
                    route="/preload",
                    handler=handle_preload
                ),
                RouteSpec(
                    method="get",
                    route="/admin/codes",
                    handler=handle_get_indexed_codes
                ),
            ]
        ),
        MongoCfg(
            url="mongodb://localhost:9006",
            database_name="orwynnTestDb",
            must_clean_db_on_destroy=True
        ),
        PreloadCfg(
            must_clean_preloads_on_destroy=True
        )
    ]
}
