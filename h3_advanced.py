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


NODE_CLASS_MAPPINGS = {
    "H3ConditionStrength": H3ConditionStrength,
    "H3ReferenceAudio": H3ReferenceAudio,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "H3ConditionStrength": "H3 Condition Strength",
    "H3ReferenceAudio": "H3 Reference Audio (stereo guard)",
}
