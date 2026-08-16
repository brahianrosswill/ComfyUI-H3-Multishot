"""H3 TAE Decode: draft-quality frames from H3 video latents in milliseconds.

Kijai ships a 9.3 MB tiny autoencoder for MiniMax-H3 (vae_approx/taeh3).
Comfy 0.32 does not know it for live previews and the full video VAE is the
slowest, most VRAM-hungry step of a draft loop - so this node decodes the
sampler's video_latents output through the TAE instead. Seed hunts and
walk-folder triage watch drafts; the real VAE renders finals.

The network is reconstructed FROM THE CHECKPOINT'S OWN SHAPES rather than
hardcoded: numbered Sequential indices, 4-D '<i>.weight' = Conv2d,
'<i>.conv.0.weight' = TAESD Block, gaps = ReLU after the stem or Upsample
between stages (the TAESD decoder grammar). state dict loads strict, so a
layout this grammar cannot express fails loudly instead of decoding garbage.
"""
import os

import torch


def _build_decoder(sd):
    import torch.nn as nn
    from comfy.taesd.taesd import Block, Clamp

    idxs = sorted({int(k.split(".")[0]) for k in sd})
    mods, last_was_stem = [], False
    for i in range(idxs[-1] + 1):
        wk, bk = "%d.weight" % i, "%d.conv.0.weight" % i
        if wk in sd and sd[wk].ndim == 4:
            o, c, kh, kw = sd[wk].shape
            mods.append(nn.Conv2d(c, o, (kh, kw), padding=(kh // 2, kw // 2),
                                  bias=("%d.bias" % i) in sd))
            last_was_stem = (i == idxs[0])
        elif bk in sd:
            n_in = sd[bk].shape[1]
            n_out = sd["%d.conv.4.weight" % i].shape[0]
            mods.append(Block(n_in, n_out))
            last_was_stem = False
        else:
            if i == 0:
                mods.append(Clamp())
            elif last_was_stem:
                mods.append(nn.ReLU())
                last_was_stem = False
            else:
                mods.append(nn.Upsample(scale_factor=2, mode="nearest"))
    return nn.Sequential(*mods)


_CACHE = {}


class H3TAEDecode:
    @classmethod
    def INPUT_TYPES(cls):
        import folder_paths
        files = [f for f in folder_paths.get_filename_list("vae_approx")
                 if "taeh3" in f.lower()] or ["taeh3.safetensors"]
        return {"required": {
            "samples": ("LATENT", {
                "tooltip": "H3 VIDEO latents - the sampler's video_latents "
                           "output, or any [B,24,T,H,W] H3 latent."}),
            "tae_name": (files,),
        }}

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("frames",)
    FUNCTION = "decode"
    CATEGORY = "video/minimax"
    DESCRIPTION = ("Draft decode through the 9.3 MB tiny autoencoder: "
                   "milliseconds and megabytes instead of the full video VAE. "
                   "Draft quality, per-frame 2D (no temporal smoothing), and "
                   "the TAE's own output resolution - for seed hunts and "
                   "triage, never for finals.")

    def decode(self, samples, tae_name):
        import comfy.model_management as mm
        import folder_paths
        from safetensors.torch import load_file

        path = folder_paths.get_full_path("vae_approx", tae_name)
        if path is None:
            raise RuntimeError(
                "taeh3 not found in models/vae_approx/. Download "
                "Kijai/MiniMax-H3-TAE (9.3 MB) and drop it there.")
        dev = mm.get_torch_device()
        key = (path, str(dev))
        if key not in _CACHE:
            sd = load_file(path)
            net = _build_decoder(sd)
            missing, unexpected = net.load_state_dict(sd, strict=False)
            if missing or unexpected:
                raise RuntimeError(
                    "taeh3 layout does not match the reconstructed decoder "
                    "(missing %s, unexpected %s) - the file changed upstream; "
                    "this node needs updating rather than guessing."
                    % (sorted(missing)[:4], sorted(unexpected)[:4]))
            _CACHE[key] = net.to(dev).eval()
            print("[H3TAEDecode] %s loaded (%d modules)"
                  % (os.path.basename(path), len(_CACHE[key])), flush=True)
        net = _CACHE[key]

        x = samples["samples"]
        if x.ndim != 5:
            raise RuntimeError("expected [B,C,T,H,W] video latent, got %s"
                               % (tuple(x.shape),))
        b, c, t, h, w = x.shape
        frames = []
        with torch.no_grad():
            for bi in range(b):
                lat = x[bi].movedim(1, 0).to(dev, torch.float32)  # [T,C,H,W]
                for i in range(0, t, 8):
                    out = net(lat[i:i + 8])
                    frames.append(out.clamp(0, 1).movedim(1, -1).cpu())
        img = torch.cat(frames, dim=0)
        print("[H3TAEDecode] %d latent rows -> %s frames at %dx%d"
              % (t * b, img.shape[0], img.shape[2], img.shape[1]), flush=True)
        return (img,)


NODE_CLASS_MAPPINGS = {"H3TAEDecode": H3TAEDecode}
NODE_DISPLAY_NAME_MAPPINGS = {"H3TAEDecode": "H3 TAE Decode (draft preview)"}
