# -*- coding: utf-8 -*-
"""Episode-assembly helpers for the two-stage reference pipeline.

Stage A renders block 1 with MiniMaxH3ReferenceToVideo (identity in pixels),
stage B chains blocks 2..N through H3MultishotSampler from stage A's last
frame, and the segments are joined in-graph. These three nodes are the glue:

  H3ScriptSplit  - one pasted episode script -> stage A prompt + stage B script
  H3LastFrame    - stage A frames -> the single chain frame for start_image
  H3ConcatAV     - stage A + stage B frames/audio -> one episode
"""
import json
import re

_BLOCK_SPLIT = re.compile(r"(?m)^---\s*$")


class H3ScriptSplit:
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
            raise ValueError("[H3ScriptSplit] script is empty - paste the "
                             "episode envelope or --- separated blocks.")
        if text.startswith("{"):
            try:
                blocks = json.loads(text)["prompts"]
            except Exception as e:
                raise ValueError(f"[H3ScriptSplit] script looks like JSON but "
                                 f"failed to parse: {e}")
        else:
            blocks = [b.strip() for b in _BLOCK_SPLIT.split(text) if b.strip()]
        blocks = [str(b).strip() for b in blocks if str(b).strip()]
        if len(blocks) < 2:
            raise ValueError(
                f"[H3ScriptSplit] {len(blocks)} block(s) parsed - this "
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


NODE_CLASS_MAPPINGS = {
    "H3ScriptSplit": H3ScriptSplit,
    "H3LastFrame": H3LastFrame,
    "H3ConcatAV": H3ConcatAV,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "H3ScriptSplit": "H3 Script Split (episode -> stage A + B)",
    "H3LastFrame": "H3 Last Frame",
    "H3ConcatAV": "H3 Concat A/V",
}
