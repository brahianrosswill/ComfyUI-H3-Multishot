from .h3_multishot_utils import (NODE_CLASS_MAPPINGS,
                                 NODE_DISPLAY_NAME_MAPPINGS)
from .h3_keyframes import (NODE_CLASS_MAPPINGS as _KF_C,
                           NODE_DISPLAY_NAME_MAPPINGS as _KF_N)
from .h3_cartridge import (NODE_CLASS_MAPPINGS as _CT_C,
                           NODE_DISPLAY_NAME_MAPPINGS as _CT_D)
from .h3_ref_folder import (NODE_CLASS_MAPPINGS as _RF_C,
                            NODE_DISPLAY_NAME_MAPPINGS as _RF_D)
from .h3_advanced import (NODE_CLASS_MAPPINGS as _AD_C,
                          NODE_DISPLAY_NAME_MAPPINGS as _AD_N)
from .h3_lora_stack import (NODE_CLASS_MAPPINGS as _LS_C,
                            NODE_DISPLAY_NAME_MAPPINGS as _LS_D)

for _c, _n in ((_KF_C, _KF_N), (_AD_C, _AD_N)):
    NODE_CLASS_MAPPINGS.update(_c)
    NODE_DISPLAY_NAME_MAPPINGS.update(_n)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]

NODE_CLASS_MAPPINGS.update(_RF_C)
NODE_DISPLAY_NAME_MAPPINGS.update(_RF_D)
NODE_CLASS_MAPPINGS.update(_CT_C)
NODE_DISPLAY_NAME_MAPPINGS.update(_CT_D)
NODE_CLASS_MAPPINGS.update(_LS_C)
NODE_DISPLAY_NAME_MAPPINGS.update(_LS_D)
