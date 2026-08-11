# -*- coding: utf-8 -*-
"""H3 Ref Folder - pull reference images from a folder, JoyEcho-style.

MiniMax-H3's reference node takes up to 9 SEPARATE image inputs. A batched
IMAGE does not work: core's loop resizes `img[:1]`, so a batch silently becomes
its first frame with no warning. This node therefore emits nine individual
IMAGE outputs (plus a count and a log string); unused outputs return None,
which core's reference loop skips explicitly (`if img is None: continue`).

Selection mirrors the JoyEcho RefPicker conventions:
  first_n  - deterministic: sorted filenames, take the first max_refs
  by_seed  - seeded shuffle of the sorted list, take max_refs
  newest   - most recently modified first

`character` (optional) narrows to `<refs_root>/<character>/` when that
subfolder exists, else to filenames containing the string - both matching how
character reference folders are laid out.
"""
import os
import random

VALID_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
MAX_SLOTS = 9


def pick_refs(refs_root, character="", pick="first_n", seed=0, max_refs=3):
    """Pure selection logic - unit-testable without ComfyUI."""
    root = refs_root
    if not os.path.isdir(root):
        raise FileNotFoundError(f"H3RefFolder: refs_root not found: {root}")
    character = (character or "").strip()
    if character and os.path.isdir(os.path.join(root, character)):
        root = os.path.join(root, character)
        names = [f for f in os.listdir(root) if f.lower().endswith(VALID_EXT)]
    else:
        names = [f for f in os.listdir(root) if f.lower().endswith(VALID_EXT)]
        if character:
            names = [f for f in names if character.lower() in f.lower()]
    if not names:
        raise FileNotFoundError(
            f"H3RefFolder: no images matching character={character!r} under {root}")
    names.sort()
    if pick == "by_seed":
        rng = random.Random(seed)
        rng.shuffle(names)
    elif pick == "newest":
        names.sort(key=lambda f: os.path.getmtime(os.path.join(root, f)),
                   reverse=True)
    chosen = names[:max(1, min(MAX_SLOTS, max_refs))]
    return [os.path.join(root, f) for f in chosen]


class H3RefFolder:
    """Folder in, up to nine separate reference images out."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "refs_root": ("STRING", {"default": "", "tooltip":
                "Folder of reference images. Absolute path, or relative to the "
                "ComfyUI input directory."}),
            "pick": (["first_n", "by_seed", "newest"], {"default": "first_n"}),
            "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff,
                             "tooltip": "Used by by_seed only."}),
            "max_refs": ("INT", {"default": 3, "min": 1, "max": MAX_SLOTS,
                                 "tooltip": "How many references to emit (model cap is 9)."}),
        }, "optional": {
            "character": ("STRING", {"default": "", "tooltip":
                "Subfolder name under refs_root, or a filename substring."}),
        }}

    RETURN_TYPES = tuple(["IMAGE"] * MAX_SLOTS + ["INT", "STRING"])
    RETURN_NAMES = tuple([f"ref_{i+1}" for i in range(MAX_SLOTS)] + ["count", "picked"])
    FUNCTION = "load"
    CATEGORY = "loaders/minimax"

    @classmethod
    def IS_CHANGED(cls, refs_root, pick, seed, max_refs, character=""):
        # folder contents can change without any widget changing
        try:
            paths = pick_refs(cls._resolve(refs_root), character, pick, seed, max_refs)
            return ";".join(f"{p}:{os.path.getmtime(p)}" for p in paths)
        except Exception:
            return float("nan")

    @staticmethod
    def _resolve(refs_root):
        p = (refs_root or "").strip().strip('"')
        if p and not os.path.isabs(p):
            import folder_paths
            p = os.path.join(folder_paths.get_input_directory(), p)
        return p

    def load(self, refs_root, pick, seed, max_refs, character=""):
        import numpy as np
        import torch
        from PIL import Image, ImageOps

        paths = pick_refs(self._resolve(refs_root), character, pick, seed, max_refs)
        images = []
        for p in paths:
            img = Image.open(p)
            img = ImageOps.exif_transpose(img).convert("RGB")
            arr = np.asarray(img, dtype=np.float32) / 255.0
            images.append(torch.from_numpy(arr)[None,])
        picked = ", ".join(os.path.basename(p) for p in paths)
        print(f"[H3RefFolder] {len(images)} ref(s): {picked}", flush=True)
        out = images + [None] * (MAX_SLOTS - len(images))
        return tuple(out + [len(images), picked])


NODE_CLASS_MAPPINGS = {"H3RefFolder": H3RefFolder}
NODE_DISPLAY_NAME_MAPPINGS = {"H3RefFolder": "H3 Ref Folder (up to 9 separate refs)"}
