from .h3_multishot_utils import (NODE_CLASS_MAPPINGS,
                                 NODE_DISPLAY_NAME_MAPPINGS)
from .h3_keyframes import (NODE_CLASS_MAPPINGS as _KF_C,
                           NODE_DISPLAY_NAME_MAPPINGS as _KF_N)
from .h3_advanced import (NODE_CLASS_MAPPINGS as _AD_C,
                          NODE_DISPLAY_NAME_MAPPINGS as _AD_N)

for _c, _n in ((_KF_C, _KF_N), (_AD_C, _AD_N)):
    NODE_CLASS_MAPPINGS.update(_c)
    NODE_DISPLAY_NAME_MAPPINGS.update(_n)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
