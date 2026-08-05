"""Keyframes anywhere in the clip, not just the first and last frame.

Stock ComfyUI accepts H3 keyframes at frame 0 and frame N-1 only. This node
accepts as many anchors as you like at any positions, by generalising the
positional maths (see h3_interior_patch.py) which stock hard-codes for the two
endpoints.

Measured behaviour, RTX 5090, 243 frames, one anchor at pixel frame 121:
  * the rendered frame most resembling the anchor image was frame 122 of 243 --
    the requested position, off by one
  * no cut: peak frame-to-frame change was 2.3x the median, i.e. the model MOVED
    to the anchor rather than jumping to it
  * the audio ran unbroken straight through the anchor

WHAT TO EXPECT -- MOVE vs CUT
Give it two images with a plausible camera path between them (same location,
different angle or framing) and H3 interpolates: a real move, arriving on time.
Give it two images with NO possible path (a kitchen and a diner) and H3 does the
only sensible thing -- it CUTS, then holds. Stock first/last behaves identically
with such a pair, so this is the model, not the node. Both are useful: one gives
you choreography, the other gives you a timed shot change inside a single
generation, which keeps the audio continuous across the cut.
"""

import torch

try:                       # 1. folder pack
    from .h3_interior_patch import ensure_interior_keyframes
except ImportError:
    try:                   # 2. loose file, dir on sys.path
        from h3_interior_patch import ensure_interior_keyframes
    except ImportError:    # 3. loose file loaded by path (ComfyUI's real loader)
        import importlib.util as _ilu
        import os as _os
        _p = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                           "h3_interior_patch.py")
        _s = _ilu.spec_from_file_location("h3_interior_patch", _p)
        _m = _ilu.module_from_spec(_s)
        _s.loader.exec_module(_m)
        ensure_interior_keyframes = _m.ensure_interior_keyframes

MAX_SLOTS = 6


def _parse_positions(text, frame_count):
    """'0, 0.5, 1' -> frame indices. <=1.0 is a fraction, >1.0 is a frame index."""
    out = []
    for tok in text.replace(";", ",").split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            v = float(tok)
        except ValueError:
            raise ValueError(f"'{tok}' in positions is not a number")
        if v < 0:
            raise ValueError(f"position {tok} is negative")
        idx = int(round(v * (frame_count - 1))) if v <= 1.0 else int(round(v))
        out.append(max(0, min(frame_count - 1, idx)))
    return out


class H3Keyframes:
    @classmethod
    def INPUT_TYPES(cls):
        opt = {f"image_{i}": ("IMAGE",) for i in range(1, MAX_SLOTS + 1)}
        return {
            "required": {
                "clip": ("CLIP",),
                "vae": ("VAE",),
                "prompt": ("STRING", {"multiline": True, "dynamicPrompts": True,
                                      "default": ""}),
                "width": ("INT", {"default": 960, "min": 32, "max": 4096,
                                  "step": 32}),
                "height": ("INT", {"default": 544, "min": 32, "max": 4096,
                                   "step": 32}),
                "length": ("INT", {
                    "default": 243, "min": 5, "max": 3600, "step": 17,
                    "tooltip": "Frames at 24fps, on H3's 17k+5 grid. "
                               "243 = ~10.1s, 362 = trained max ~15.1s."}),
                "positions": ("STRING", {
                    "default": "0, 0.5",
                    "tooltip": "One position per connected image, in order. "
                               "A value of 1.0 or less is a FRACTION of the "
                               "clip (0 = first frame, 0.5 = halfway, 1 = last). "
                               "A value above 1 is an absolute frame index. "
                               "Example: '0, 0.5, 1' anchors the start, the "
                               "middle and the end."}),
            },
            "optional": opt,
        }

    RETURN_TYPES = ("CONDITIONING", "LATENT", "STRING")
    RETURN_NAMES = ("positive", "latent", "info")
    FUNCTION = "build"
    CATEGORY = "conditioning/video_models"
    DESCRIPTION = ("MiniMax H3 conditioning with keyframes at ARBITRARY "
                   "positions, not just first/last. Connect images to the "
                   "image_N slots and give one position per image.")

    def build(self, clip, vae, prompt, width, height, length, positions,
              **kwargs):
        import node_helpers
        from comfy_extras import nodes_minimax_h3 as mmh3

        patched, patch_msg = ensure_interior_keyframes()

        latent, frame_count = mmh3._empty_av_latent(width, height, length)

        imgs = [kwargs.get(f"image_{i}") for i in range(1, MAX_SLOTS + 1)]
        imgs = [im for im in imgs if im is not None]
        idxs = _parse_positions(positions, frame_count)

        if not imgs:
            raise ValueError(
                "H3 Keyframes: connect at least one image (image_1..image_6). "
                "For pure text-to-video use the stock t2va node instead.")
        if len(idxs) != len(imgs):
            raise ValueError(
                f"H3 Keyframes: {len(imgs)} image(s) connected but "
                f"{len(idxs)} position(s) given ('{positions}'). "
                f"Give exactly one position per connected image, in order.")

        # ascending, and no two anchors on the same frame
        order = sorted(range(len(idxs)), key=lambda i: idxs[i])
        idxs = [idxs[i] for i in order]
        imgs = [imgs[i] for i in order]
        for a, b in zip(idxs, idxs[1:]):
            if a == b:
                raise ValueError(
                    f"H3 Keyframes: two anchors resolve to the same frame "
                    f"({a}). Move them apart -- at {frame_count} frames, one "
                    f"frame is {1.0/(frame_count-1):.4f} of the clip.")

        interior = [i for i in idxs if i not in (0, frame_count - 1)]
        if interior and not patched:
            raise ValueError(
                f"H3 Keyframes: interior anchors at {interior} need the "
                f"positional patch, which could not be applied: {patch_msg}. "
                f"Anchors at frame 0 and frame {frame_count - 1} still work.")

        keyframes, enc_images, notes = [], [], []
        for i, (img, idx) in enumerate(zip(imgs, idxs)):
            # match stock: the first frame sets the geometry (stretch to fit),
            # every follower is aspect-preserving cover-cropped
            mode = "disabled" if idx == 0 else "center"
            resized = mmh3._resize(img[:1], width, height, mode)
            enc_images.append(resized)
            keyframes.append({"resolved_frame_index": int(idx),
                              "image": resized})
            notes.append(f"{idx}({idx/24.0:.2f}s)")

        tokens = clip.tokenize(prompt, images=enc_images)
        cond = clip.encode_from_tokens_scheduled(tokens)

        for kf in keyframes:
            kf["latent"] = vae.encode(kf.pop("image"))
        cond = node_helpers.conditioning_set_values(cond, {
            "minimax_keyframes": keyframes,
            "minimax_frame_count": frame_count,
        })

        # --- free the text encoder before the DiT loads ---------------------
        # Same reason as the multishot sampler: the 32B VL encoder (~16.5GB even
        # at Q4) and the H3 DiT (~25GB) do not co-fit on a 32GB card. Left
        # resident, the DiT loads PARTIALLY and streams ~19GB from system RAM on
        # every sampling step -- measured at ~60min vs ~15min for the same
        # render. Conditioning is fully computed by this point, so the encoder
        # weights are safe to evict; this node runs before the guider/sampler
        # pull the DiT in, which is exactly the window that matters.
        import comfy.model_management as _mm
        try:
            clip.patcher.model.to(_mm.text_encoder_offload_device())
        except Exception as _e:
            print(f"[H3Keyframes] TE offload skipped: {_e}", flush=True)
        try:
            _dev = _mm.get_torch_device()
            _mm.free_memory(_mm.get_total_memory(_dev) * 0.9, _dev)
            _mm.soft_empty_cache()
            _free = _mm.get_free_memory(_dev) / (1024 ** 3)
            print(f"[H3Keyframes] TE evicted; {_free:.1f} GB free for the DiT",
                  flush=True)
        except Exception as _e:
            print(f"[H3Keyframes] VRAM purge skipped: {_e}", flush=True)
        # --------------------------------------------------------------------

        info = (f"{frame_count} frames ({frame_count/24.0:.2f}s) | "
                f"{len(keyframes)} keyframe(s) at {', '.join(notes)}"
                + (f" | {patch_msg}" if interior else ""))
        print("[H3Keyframes] " + info, flush=True)
        return (cond, latent, info)


NODE_CLASS_MAPPINGS = {"H3Keyframes": H3Keyframes}
NODE_DISPLAY_NAME_MAPPINGS = {"H3Keyframes": "H3 Keyframes (any position)"}
