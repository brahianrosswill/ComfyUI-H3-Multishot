# -*- coding: utf-8 -*-
"""Episode-assembly helpers for the two-stage reference pipeline.

Stage A renders block 1 with MiniMaxH3ReferenceToVideo (identity in pixels),
stage B chains blocks 2..N through H3MultishotSampler from stage A's last
frame, and the segments are joined in-graph. These three nodes are the glue:

  H3EpisodeSplit  - one pasted episode script -> stage A prompt + stage B script
  H3LastFrame    - stage A frames -> the single chain frame for start_image
  H3ConcatAV     - stage A + stage B frames/audio -> one episode
"""
import json
import re

_BLOCK_SPLIT = re.compile(r"(?m)^---\s*$")


class H3EpisodeSplit:
    """Split an episode script into the stage A prompt and stage B envelope.

    Accepts either the one-line JSON envelope {"prompts": [...]} (the LPFF
    entry format) or raw blocks separated by --- lines. `bindings` is
    prepended to block 1 only - reference-image identity lines like
    "<Picture 1>, <Picture 2> are the same person (Zara)." belong with the
    ref2va stage, never in the I2V chain.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "script": ("STRING", {"multiline": True, "default": "", "tooltip":
                "The whole episode: either the one-line JSON envelope "
                '{"prompts": [...]} or raw blocks separated by --- lines.'}),
            "bindings": ("STRING", {"multiline": True, "default": "", "tooltip":
                "<Picture N> identity lines, prepended to block 1 only. "
                "Keep in sync with which reference images are unmuted."}),
        }}

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("block1_prompt", "rest_script", "info")
    FUNCTION = "split"
    CATEGORY = "video/minimax"

    def split(self, script, bindings):
        text = (script or "").strip()
        if not text:
            raise ValueError("[H3EpisodeSplit] script is empty - paste the "
                             "episode envelope or --- separated blocks.")
        if text.startswith("{"):
            try:
                blocks = json.loads(text)["prompts"]
            except Exception as e:
                raise ValueError(f"[H3EpisodeSplit] script looks like JSON but "
                                 f"failed to parse: {e}")
        else:
            blocks = [b.strip() for b in _BLOCK_SPLIT.split(text) if b.strip()]
        blocks = [str(b).strip() for b in blocks if str(b).strip()]
        if len(blocks) < 2:
            raise ValueError(
                f"[H3EpisodeSplit] {len(blocks)} block(s) parsed - this "
                "workflow chains stage B after stage A, so it needs at least "
                "2. For a single-block scene use the plain Hard Mode "
                "reference workflow instead.")
        b = (bindings or "").strip()
        block1 = (b + "\n" + blocks[0]) if b else blocks[0]
        rest = json.dumps({"prompts": blocks[1:]}, ensure_ascii=False)
        info = (f"{len(blocks)} blocks -> stage A renders block 1, "
                f"stage B chains {len(blocks) - 1} block(s) "
                f"(~{len(blocks) * 15.1:.0f}s total at 362f/block)")
        return (block1, rest, info)


class H3LastFrame:
    """Return the last frame of a batch - the I2V chain frame."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"images": ("IMAGE", {"tooltip":
            "Stage A frames; the final frame seeds stage B's start_image."})}}

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "take"
    CATEGORY = "image/batch"

    def take(self, images):
        return (images[-1:],)


class H3ConcatAV:
    """Concatenate two video+audio segments into one continuous take."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images_a": ("IMAGE",), "audio_a": ("AUDIO",),
            "images_b": ("IMAGE",), "audio_b": ("AUDIO",),
        }}

    RETURN_TYPES = ("IMAGE", "AUDIO")
    RETURN_NAMES = ("images", "audio")
    FUNCTION = "concat"
    CATEGORY = "video/minimax"

    def concat(self, images_a, audio_a, images_b, audio_b):
        import torch
        if tuple(images_a.shape[1:3]) != tuple(images_b.shape[1:3]):
            raise ValueError(
                f"[H3ConcatAV] frame sizes differ: A "
                f"{tuple(images_a.shape[1:3])} vs B "
                f"{tuple(images_b.shape[1:3])} - both stages must render at "
                "the same width/height.")
        images = torch.cat((images_a, images_b), dim=0)
        wa, wb = audio_a["waveform"], audio_b["waveform"]
        sa = int(audio_a["sample_rate"])
        if sa != int(audio_b["sample_rate"]):
            raise ValueError(f"[H3ConcatAV] sample rates differ: {sa} vs "
                             f"{int(audio_b['sample_rate'])}")
        if wa.shape[1] != wb.shape[1]:
            # mono/stereo mismatch: upmix the narrower side
            c = max(wa.shape[1], wb.shape[1])
            wa = wa.expand(-1, c, -1) if wa.shape[1] == 1 else wa
            wb = wb.expand(-1, c, -1) if wb.shape[1] == 1 else wb
        audio = {"waveform": torch.cat((wa, wb), dim=-1), "sample_rate": sa}
        return (images, audio)


class H3AutoRefs:
    """Auto-select reference images per character from folders.

    The RiftCast Studio pattern (JoyEcho_RefPicker) adapted to ref2va: a refs
    root holds one subfolder per character; the prompt's descriptive prose is
    scanned for folder names as whole words (dialogue is stripped first, so a
    character merely TALKED ABOUT never matches); each matched character
    contributes up to max_per_character images, in first-mention order, up to
    the model's 9-slot cap; and the matching <Picture N> identity bindings are
    generated and prepended to the prompt automatically.
    """

    MAX_SLOTS = 9

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "prompt_text": ("STRING", {"forceInput": True, "tooltip":
                "Block-1 text; scanned for character folder names."}),
            "max_per_character": ("INT", {"default": 3, "min": 1, "max": 9,
                "tooltip": "Images per matched character (sorted order; "
                "front/three-quarter/profile sets hold identity best)."}),
        }, "optional": {
            "refs_root": ("STRING", {"default": "", "tooltip":
                "Folder holding one subfolder per character. Relative paths "
                "resolve under input/. Empty = input/h3_refs/."}),
            "characters": ("STRING", {"default": "", "tooltip":
                "Explicit comma list of character folders - overrides the "
                "prompt scan entirely when set."}),
            "overrides": ("STRING", {"default": "", "tooltip":
                "Folder remaps, e.g. 'zara=zara_preflash' to swap a "
                "character's ref set for specific scenes. Comma-separated."}),
            "on_no_match": (["error", "no_reference"], {"default": "error",
                "tooltip": "error = stop the run when no character matches "
                "(an identity render without refs is a wasted render)."}),
        }}

    RETURN_TYPES = tuple(["IMAGE"] * 9 + ["STRING", "STRING"])
    RETURN_NAMES = tuple([f"ref_{i+1}" for i in range(9)]
                         + ["prompt_out", "report"])
    FUNCTION = "pick"
    CATEGORY = "video/minimax"

    @staticmethod
    def _root(refs_root):
        import os
        import folder_paths
        r = (refs_root or "").strip() or "h3_refs"
        if not os.path.isabs(r):
            r = os.path.join(folder_paths.get_input_directory(), r)
        return r

    @classmethod
    def IS_CHANGED(cls, prompt_text, max_per_character, refs_root="",
                   characters="", overrides="", on_no_match="error"):
        import os
        root = cls._root(refs_root)
        sig = [str(hash(prompt_text or "")), str(max_per_character),
               characters, overrides, root]
        try:
            for d in sorted(os.listdir(root)):
                p = os.path.join(root, d)
                if os.path.isdir(p):
                    fs = sorted(os.listdir(p))
                    sig.append(f"{d}:{len(fs)}")
        except OSError:
            pass
        return "|".join(sig)

    def pick(self, prompt_text, max_per_character, refs_root="",
             characters="", overrides="", on_no_match="error"):
        import os
        import numpy as np
        import torch
        from PIL import Image, ImageOps

        root = self._root(refs_root)
        try:
            dirs = sorted(d for d in os.listdir(root)
                          if os.path.isdir(os.path.join(root, d)))
        except OSError:
            dirs = []
        remap = {}
        for pair in (overrides or "").split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                remap[k.strip().lower()] = v.strip()

        if (characters or "").strip():
            matched = [c.strip() for c in characters.split(",") if c.strip()]
        else:
            # strip dialogue so absent characters spoken about never match
            # (same scrub as JoyEcho_RefPicker, field-proven)
            scrub = prompt_text or ""
            try:
                _d = json.loads(scrub)
                arr = _d.get("prompts") if isinstance(_d, dict) else None
                if isinstance(arr, list) and arr:
                    scrub = " ".join(str(x) for x in arr)
            except (ValueError, TypeError):
                pass
            scrub = re.sub(r'\\"(?:[^"\\]|\\.)*?\\"', " ", scrub)
            scrub = re.sub(r'"(?:[^"\\]|\\.)*?"', " ", scrub)
            scrub = re.sub(r"says,\s*'(?:[^'])*?'", " ", scrub)
            low = scrub.lower()
            found = []
            for d in dirs:
                m = re.search(r"\b" + re.escape(d.lower()) + r"\b", low)
                if m:
                    found.append((m.start(), d))
            found.sort()
            matched = [d for _, d in found[:3]]

        images, binds, lines, pic = [], [], [], 1
        for name in matched:
            folder = remap.get(name.lower(), name)
            fdir = os.path.join(root, folder)
            try:
                files = sorted(f for f in os.listdir(fdir) if
                               f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")))
            except OSError:
                files = []
            if not files:
                print(f"[H3AutoRefs] {folder}/ matched but has no images; "
                      "skipping.", flush=True)
                continue
            nums = []
            for f in files[:max_per_character]:
                if len(images) >= self.MAX_SLOTS:
                    break
                img = Image.open(os.path.join(fdir, f))
                img = ImageOps.exif_transpose(img).convert("RGB")
                arr = np.asarray(img).astype(np.float32) / 255.0
                images.append(torch.from_numpy(arr)[None, ...])
                nums.append(f"<Picture {pic}>")
                lines.append(f"{folder}/{f} -> <Picture {pic}>")
                pic += 1
            if nums:
                disp = name.replace("_", " ").title()
                binds.append(f"{', '.join(nums)} "
                             f"{'is' if len(nums) == 1 else 'are'} "
                             f"the same person ({disp}).")

        if not images:
            msg = (f"[H3AutoRefs] no character matched. Folders under "
                   f"{root}: {dirs or '(none)'}")
            if on_no_match == "error":
                raise ValueError(msg + " - name the character in the prose, "
                                 "set `characters`, or switch on_no_match.")
            print(msg + " - continuing WITHOUT references.", flush=True)
            return tuple([None] * self.MAX_SLOTS
                         + [prompt_text, "(no references)"])

        prompt_out = "\n".join(binds) + "\n" + (prompt_text or "")
        report = f"{len(images)} ref(s): " + "; ".join(lines)
        print(f"[H3AutoRefs] {report}", flush=True)
        out = images + [None] * (self.MAX_SLOTS - len(images))
        return tuple(out + [prompt_out, report])


NODE_CLASS_MAPPINGS = {
    "H3EpisodeSplit": H3EpisodeSplit,
    "H3LastFrame": H3LastFrame,
    "H3ConcatAV": H3ConcatAV,
    "H3AutoRefs": H3AutoRefs,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "H3EpisodeSplit": "H3 Episode Split (stage A + B)",
    "H3LastFrame": "H3 Last Frame",
    "H3ConcatAV": "H3 Concat A/V",
    "H3AutoRefs": "H3 Auto Refs (folders, by prompt)",
}
