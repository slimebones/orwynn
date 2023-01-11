from typing import Any
from copy import deepcopy
import dictdiffer

from orwynn import validation
from orwynn.error.MalfunctionError import MalfunctionError
from orwynn.mp.dictpp import dictpp


def patch(
    to_be_patched: dictpp,
    source: dictpp,
    should_deepcopy: bool = True
) -> dictpp:
    """Patch one dictionary by another.

    Args:
        to_be_patched:
            Dict to be patched.
        source:
            Source dict to use for patching.
        should_deepcopy (optional):
            Whether deepcopy() should be performed on patched dict. Defaults
            to True. If False is passed, it is convenient to not accept
            returned dict since it is the same as passed one to patch.

    Returns:
        Patched dictionary.
    """
    validation.validate(to_be_patched, dictpp)
    validation.validate(source, dictpp)

    patched: dictpp

    if should_deepcopy:
        patched = deepcopy(to_be_patched)
    else:
        patched = to_be_patched

    diff = dictdiffer.diff(to_be_patched, source)

    event_name: str
    location: str
    change: Any

    for event in diff:
        # Unpack event tuple
        event_name, location, change = event
        # How dictdiffer event_name, location and change would like for a
        # reference:
        #   change BurgerShot.menu.cola (1.5, 1.8)
        #   add BurgerShot.menu [('pizza', 4.1), ('fried_chicken', 3.5)]

        # Consider only adding and changing events
        if event_name == "add":
            final_location: str
            for addition in change:
                # Calculate final location in patched dict
                if location:
                    final_location = ".".join([location, addition[0]])
                else:
                    final_location = addition[0]
                patched[final_location] = addition[1]

        elif event_name == "change":
            if location == "":
                raise MalfunctionError(
                    "on change events location shouldn't be empty"
                )
            patched[location] = change[1]

    return patched