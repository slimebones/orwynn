from orwynn.base.config.config import Config
from orwynn.base.indication.indication import Indication
from orwynn.base.model.model import Model
from orwynn.boot.boot_mode import BootMode


class BootConfig(Config):
    """Contains information about boot.

    Attributes:
        mode:
            Boot mode.
        root_dir:
            Root directory of the boot.
    """
    SOURCE = "boot"

    mode: BootMode
    root_dir: str
    api_indication: Indication
