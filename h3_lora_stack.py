# -*- coding: utf-8 -*-
"""H3 LoRA Stack - up to four LoRAs on the H3 DiT in one node.

MODEL-only on purpose: H3's text encoder is a separate CLIP object and H3
LoRAs published so far (e.g. the 4-step turbo distill) target the DiT blocks.
Loading goes through comfy.sd.load_lora_for_models with clip=None - the exact
path core LoraLoaderModelOnly uses, which is render-proven on the GGUF-loaded
H3 models (the turbo A/B series).

Slots left on "None" are skipped, so the node is inert by default and safe to
sit in every workflow. Measured turbo reference (see the pack docs): the
4-step distill LoRA @1.0 with euler+beta runs well at 12 steps for dialogue
scenes and 8 steps for voiceover-only scenes.
"""
import folder_paths

MAX_SLOTS = 4
_NONE = "None"


class H3LoraStack:
    @classmethod
    def INPUT_TYPES(cls):
        loras = [_NONE] + folder_paths.get_filename_list("loras")
        req = {"model": ("MODEL",)}
        for i in range(1, MAX_SLOTS + 1):
            req[f"lora_{i}"] = (loras, {"default": _NONE})
            req[f"strength_{i}"] = ("FLOAT", {
                "default": 1.0, "min": -2.0, "max": 2.0, "step": 0.05})
        return {"required": req}

    RETURN_TYPES = ("MODEL",)
    RETURN_NAMES = ("model",)
    FUNCTION = "apply"
    CATEGORY = "loaders/minimax"

    def apply(self, model, **kw):
        import comfy.sd
        import comfy.utils
        m = model
        applied = []
        for i in range(1, MAX_SLOTS + 1):
            name = kw.get(f"lora_{i}", _NONE)
            strength = float(kw.get(f"strength_{i}", 1.0))
            if not name or name == _NONE or strength == 0.0:
                continue
            path = folder_paths.get_full_path("loras", name)
            if path is None:
                raise RuntimeError(f"H3LoraStack: LoRA not found: {name}")
            lora = comfy.utils.load_torch_file(path, safe_load=True)
            m, _ = comfy.sd.load_lora_for_models(m, None, lora, strength, 0)
            applied.append(f"{name} @{strength:g}")
        print("[H3LoraStack] " + (", ".join(applied) if applied else
                                  "no LoRAs active (all slots None)"),
              flush=True)
        return (m,)


NODE_CLASS_MAPPINGS = {"H3LoraStack": H3LoraStack}
NODE_DISPLAY_NAME_MAPPINGS = {"H3LoraStack": "H3 LoRA Stack (up to 4)"}
