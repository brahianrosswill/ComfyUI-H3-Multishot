# -*- coding: utf-8 -*-
"""AV-memory-bank probe: can ref2va conditioning coexist with a start-frame
keyframe in one generation?

Why this might work at all: comfy's PackedLayout ALREADY composes both -
keyframe cond rows pack right after text, ref rows after them, one shared
row cursor (comfy/ldm/minimax/model.py:297). The recorded refs+keyframes
crash is a plumbing bug in MiniMaxH3.extra_conds (comfy/model_base.py:2098):
when both keys are present, the refs branch OVERWRITES payload
["cond_video_latents"] instead of appending, so the packed sequence has
more cond rows than latents. This module:

  1. monkey-patches extra_conds to MERGE (keyframes first, matching the
     layout's segment order) - in-process, same pattern as the interior
     keyframes patch, no core file edits;
  2. adds H3KeyframeInject: put a frame-0 (and optional last-frame)
     keyframe onto an EXISTING conditioning (e.g. ref2va's output).

Whether the WEIGHTS tolerate the combination is the open question the
probe render answers. If they do, the full JoyEcho-style AV bank (voice +
face memory + seamless chaining) is buildable on H3.
"""

import comfy.model_base as _mb
import node_helpers


def _apply_merge_patch():
    if getattr(_mb.MiniMaxH3.extra_conds, "_h3_avbank_merge", False):
        return
    _orig = _mb.MiniMaxH3.extra_conds

    def extra_conds(self, **kwargs):
        out = _orig(self, **kwargs)
        kf = kwargs.get("minimax_keyframes")
        refs = kwargs.get("minimax_refs")
        if kf and refs:
            payload = out["minimax_payload"].cond
            # layout packs keyframe cond rows FIRST, then ref rows - the
            # latent list must match that order
            payload["cond_video_latents"] = (
                [k["latent"] for k in kf]
                + [r["latent"] for r in refs if "latent" in r])
            print(f"[H3AVBank] merged cond latents: {len(kf)} keyframe(s) + "
                  f"{sum(1 for r in refs if 'latent' in r)} ref(s)", flush=True)
        return out

    extra_conds._h3_avbank_merge = True
    _mb.MiniMaxH3.extra_conds = extra_conds
    print("[H3AVBank] extra_conds merge patch active "
          "(refs + keyframes now compose)", flush=True)


_apply_merge_patch()


class H3KeyframeInject:
    """Add a frame-0 start keyframe to existing conditioning (ref2va etc.).

    The keyframe is what the video PHYSICALLY continues from; the refs on
    the incoming conditioning stay what the encoder looks at for identity.
    Requires the extra_conds merge patch in this module (applied at import).
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "conditioning": ("CONDITIONING",),
            "vae": ("VAE",),
            "start_image": ("IMAGE",),
            "width": ("INT", {"default": 544, "min": 32, "max": 4096, "step": 32}),
            "height": ("INT", {"default": 960, "min": 32, "max": 4096, "step": 32}),
            "length": ("INT", {"default": 362, "min": 5, "max": 3600, "step": 17,
                "tooltip": "Must match the generation's frame count."}),
        }, "optional": {
            "end_image": ("IMAGE", {"tooltip": "Optional last-frame anchor."}),
        }}

    RETURN_TYPES = ("CONDITIONING",)
    FUNCTION = "inject"
    CATEGORY = "model/conditioning/minimax"

    def inject(self, conditioning, vae, start_image, width, height, length,
               end_image=None):
        from comfy_extras.nodes_minimax_h3 import _resize, align_frame_count
        frame_count = align_frame_count(max(5, length))
        keyframes = [{"resolved_frame_index": 0,
                      "latent": vae.encode(_resize(start_image[:1], width, height, "disabled"))}]
        if end_image is not None:
            keyframes.append({"resolved_frame_index": frame_count - 1,
                              "latent": vae.encode(_resize(end_image[:1], width, height, "center"))})
        out = node_helpers.conditioning_set_values(conditioning, {
            "minimax_keyframes": keyframes,
            "minimax_frame_count": frame_count,
        })
        print(f"[H3AVBank] injected {len(keyframes)} keyframe(s) at "
              f"{[k['resolved_frame_index'] for k in keyframes]} "
              f"(frame_count {frame_count})", flush=True)
        return (out,)


NODE_CLASS_MAPPINGS = {"H3KeyframeInject": H3KeyframeInject}
NODE_DISPLAY_NAME_MAPPINGS = {
    "H3KeyframeInject": "H3 Keyframe Inject (refs + start frame PROBE)"}
