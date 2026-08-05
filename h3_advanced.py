"""Two H3 controls that the core reads but no stock node ever sets.

1. H3 Condition Strength
   `comfy/model_base.py` reads `minimax_visual_cond_noise_aug` and
   `minimax_audio_cond_noise_aug` off the conditioning, but nothing in ComfyUI
   writes them, so they always sit at their defaults (0.999 and 1.0). They do
   two things inside the DiT, both in `comfy/ldm/minimax/model.py`:

       r = aug * r + (1.0 - aug) * noise        # _cond_video_rows / _cond_audio_rows
       seg_t["cond"] = max(t_v, vis_aug)        # the timestep the cond rows sit at

   So it is an anchor-strength dial: 1.0 feeds the reference/keyframe latent in
   perfectly clean, lower values blend noise into it and let the model drift
   further from the supplied frame.

2. H3 Reference Audio (stereo guard)
   The H3 audio VAE encodes `[B, 2, L]` -> `[B, 32, 2, T]` and `PackedLayout`
   reserves exactly `T * 2` rows, with `unpack_audio` hardcoding `ch=2`. Feed a
   MONO reference clip and you get T rows against 2T reserved, which dies as a
   shape mismatch deep in the model with no hint about the cause. Nothing in the
   stock node converts channels. This node makes the fix explicit.
"""

import torch


class H3ConditionStrength:
    """Set how strongly keyframe / reference conditioning is trusted."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "conditioning": ("CONDITIONING",),
                "visual_strength": ("FLOAT", {
                    "default": 0.999, "min": 0.0, "max": 1.0, "step": 0.001,
                    "tooltip": "How clean the keyframe / reference IMAGE latents "
                               "are fed in. 1.0 = pristine (strongest adherence). "
                               "Lower blends noise into them, letting the model "
                               "drift further from the supplied frame. Core "
                               "default is 0.999."}),
                "audio_strength": ("FLOAT", {
                    "default": 1.0, "min": 0.0, "max": 1.0, "step": 0.001,
                    "tooltip": "Same, for reference AUDIO latents (ref2va only). "
                               "Core default is 1.0."}),
            },
        }

    RETURN_TYPES = ("CONDITIONING",)
    FUNCTION = "apply"
    CATEGORY = "conditioning/video_models"
    DESCRIPTION = ("MiniMax H3: how strongly keyframe/reference conditioning is "
                   "trusted. Only affects conditioning that HAS keyframes or "
                   "references - it does nothing on a plain text prompt.")

    def apply(self, conditioning, visual_strength, audio_strength):
        import node_helpers
        out = node_helpers.conditioning_set_values(conditioning, {
            "minimax_visual_cond_noise_aug": float(visual_strength),
            "minimax_audio_cond_noise_aug": float(audio_strength),
        })
        has_anchor = any(("minimax_keyframes" in d or "minimax_refs" in d)
                         for _, d in conditioning)
        note = "" if has_anchor else ("  WARNING: this conditioning has no "
                                      "keyframes or references, so these values "
                                      "will have no effect")
        print(f"[H3CondStrength] visual={visual_strength} audio={audio_strength}"
              f"{note}", flush=True)
        return (out,)


class H3ReferenceAudio:
    """Make an AUDIO clip safe to use as an H3 reference (ref2va)."""

    VAE_SR = 32000

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "max_seconds": ("FLOAT", {
                    "default": 10.0, "min": 0.5, "max": 60.0, "step": 0.5,
                    "tooltip": "Trim the reference to at most this long. "
                               "Reference rows sit in the packed sequence for "
                               "EVERY sampling step, so a long reference costs "
                               "speed on every step, not just once."}),
            },
        }

    RETURN_TYPES = ("AUDIO",)
    FUNCTION = "prep"
    CATEGORY = "conditioning/video_models"
    DESCRIPTION = ("MiniMax H3: force a reference audio clip to stereo 32 kHz. "
                   "A MONO reference crashes the sampler with an unhelpful shape "
                   "mismatch, because the layout reserves two channels.")

    def prep(self, audio, max_seconds):
        wav = audio["waveform"]
        sr = int(audio["sample_rate"])
        notes = []

        if wav.ndim == 2:                      # [C, L] -> [1, C, L]
            wav = wav.unsqueeze(0)
        wav = wav[:1]                          # the encoder uses batch item 0 only

        ch = wav.shape[1]
        if ch == 1:
            wav = wav.repeat(1, 2, 1)
            notes.append("mono -> stereo (duplicated)")
        elif ch > 2:
            wav = wav[:, :2]
            notes.append(f"{ch}ch -> first 2")

        if sr != self.VAE_SR:
            try:
                import torchaudio
                wav = torchaudio.functional.resample(wav, sr, self.VAE_SR)
                notes.append(f"{sr} -> {self.VAE_SR} Hz")
                sr = self.VAE_SR
            except Exception as e:
                notes.append(f"resample skipped ({e}); the node resamples anyway")

        limit = int(max_seconds * sr)
        if wav.shape[-1] > limit:
            notes.append(f"trimmed {wav.shape[-1]/sr:.1f}s -> {max_seconds:.1f}s")
            wav = wav[..., :limit]

        print(f"[H3RefAudio] {wav.shape[1]}ch @{sr}Hz, "
              f"{wav.shape[-1]/sr:.2f}s"
              + ("  |  " + "; ".join(notes) if notes else "  |  already valid"),
              flush=True)
        return ({"waveform": wav.contiguous(), "sample_rate": sr},)


class H3FreeTextEncoder:
    """Evict the text encoder before the DiT loads. Conditioning passes through.

    The samplers in this pack do this internally, but the STOCK H3 nodes do not
    -- there is no free_memory / text_encoder_offload call anywhere in
    comfy_extras/nodes_minimax_h3.py. So any graph built on the stock
    reference-to-video or image-to-video nodes keeps the ~16.5GB Qwen3-VL
    encoder resident while the ~25GB DiT loads, which on a 32GB card means the
    DiT loads PARTIALLY and streams the remainder from system RAM on every
    sampling step.

    Drop this between the conditioning node and the guider. Conditioning is
    fully computed by then, so the encoder weights are safe to release, and the
    guider/sampler pull the DiT in immediately afterwards -- which is exactly
    the window that matters.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"conditioning": ("CONDITIONING",),
                             "clip": ("CLIP",)}}

    RETURN_TYPES = ("CONDITIONING",)
    FUNCTION = "free"
    CATEGORY = "conditioning/video_models"
    DESCRIPTION = ("Free the text encoder from VRAM before sampling. Use with "
                   "the STOCK MiniMax H3 nodes, which never do this. "
                   "Conditioning passes through untouched.")

    def free(self, conditioning, clip):
        """Unload the encoder outright. Conditioning is already computed."""
        import comfy.model_management as mm

        dev = mm.get_torch_device()
        before = mm.get_free_memory(dev) / (1024 ** 3)

        # Do NOT use free_memory(target): it is a request for a free-memory
        # TARGET, and get_free_memory already counts evictable weights as free,
        # so the target is met immediately and nothing is unloaded. Unload the
        # model objects themselves.
        n = 0
        try:
            loaded = list(getattr(mm, "current_loaded_models", []))
            want = None
            try:
                want = clip.patcher
            except Exception:
                want = None
            for lm in loaded:
                mp = getattr(lm, "model", None)
                if want is not None and mp is not want:
                    continue
                try:
                    lm.model_unload()
                    if lm in mm.current_loaded_models:
                        mm.current_loaded_models.remove(lm)
                    n += 1
                except Exception:
                    pass
        except Exception as e:
            print(f"[H3FreeTE] targeted unload failed: {e}", flush=True)

        if n == 0:
            # Could not identify the encoder among the loaded models -- fall
            # back to unloading everything. Safe here: conditioning is done, and
            # the VAE reloads on demand after sampling.
            try:
                mm.unload_all_models()
                n = -1
            except Exception as e:
                print(f"[H3FreeTE] unload_all_models failed: {e}", flush=True)

        try:
            mm.soft_empty_cache()
        except Exception:
            pass

        after = mm.get_free_memory(dev) / (1024 ** 3)
        how = "all models" if n == -1 else f"{n} model(s)"
        print(f"[H3FreeTE] unloaded {how}; {before:.1f} -> {after:.1f} GB free",
              flush=True)
        return (conditioning,)


NODE_CLASS_MAPPINGS = {
    "H3ConditionStrength": H3ConditionStrength,
    "H3ReferenceAudio": H3ReferenceAudio,
    "H3FreeTextEncoder": H3FreeTextEncoder,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "H3ConditionStrength": "H3 Condition Strength",
    "H3ReferenceAudio": "H3 Reference Audio (stereo guard)",
    "H3FreeTextEncoder": "H3 Free Text Encoder (VRAM)",
}
