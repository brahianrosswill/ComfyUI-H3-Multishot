# -*- coding: utf-8 -*-
"""H3 multishot utilities - JoyEcho-style single-script prompting for the
MiniMax H3 chained workflow. One node, no dependencies.

Accepts the same script formats the JoyEcho stack uses:
  - JSON: {"prompts": ["shot 1 ...", "shot 2 ...", "shot 3 ..."]}
  - plain text with --- separators between shots
Feeds up to 4 shot prompts as separate STRING outputs. Missing shots fall
back to the previous shot's prompt so a 2-shot script still runs a 3-shot
graph without erroring.
"""
import json
import re


def _parse_script(text):
    """JoyEcho script -> list of shot prompts. JSON {"prompts": [...]} or
    plain text with --- separators. Malformed JSON fails LOUD."""
    text = (text or "").strip()
    shots = []
    if text.startswith("{") or text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                shots = [str(p) for p in data.get("prompts", [])]
            elif isinstance(data, list):
                shots = [str(p) for p in data]
        except json.JSONDecodeError as e:
            raise ValueError(
                f"H3 script looks like JSON but does not parse ({e}). "
                f"Common cause: a doubled {{ on the first lines, or a "
                f"missing comma/quote. Fix the script or use plain prompts "
                f"separated by --- lines.")
    if not shots:
        shots = [b.strip().replace('\\"', '"')
                 for b in re.split(r"(?m)^---\s*$", text) if b.strip()]
    if not shots:
        shots = [text]
    return shots


class H3ScriptSplit:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"script": ("STRING", {
            "multiline": True, "dynamicPrompts": False,
            "default": "Shot 1 prompt goes here.\n---\n"
                       "Shot 2 prompt goes here.\n---\n"
                       "Shot 3 prompt goes here.",
            "tooltip": "One prompt per shot, separated by --- on its own "
                       "line. (JSON {\"prompts\": [...]} also accepted, for "
                       "generated scripts.)"}),
            "shot_count": ("INT", {
                "default": 0, "min": 0, "max": 3,
                "tooltip": "This workflow ALWAYS renders 3 segments and "
                           "joins them (~30s master). 0 = count from the "
                           "script. 3 = three scenes. 2 = the third segment "
                           "continues scene 2. 1 = one scene sustained for "
                           "the full 30s. Scripts with >3 prompts: extras "
                           "are dropped (see console)."}),
        }}

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "INT")
    RETURN_NAMES = ("shot_1", "shot_2", "shot_3", "shot_4", "shot_count")
    FUNCTION = "split"
    CATEGORY = "conditioning/minimax"

    def split(self, script, shot_count=0):
        shots = _parse_script(script)
        if shot_count and shot_count > 0:
            if len(shots) > shot_count:
                print(f"[H3ScriptSplit] shot_count={shot_count}: dropping "
                      f"{len(shots) - shot_count} extra script shot(s).",
                      flush=True)
                shots = shots[:shot_count]
            while len(shots) < shot_count:
                shots.append(shots[-1])
        n = len(shots)
        if n < 3:
            print(f"[H3ScriptSplit] script has {n} shot(s); a 3-shot graph "
                  f"will render the last prompt {3 - n} extra time(s) as a "
                  f"continuation.", flush=True)
        elif n > 3:
            print(f"[H3ScriptSplit] script has {n} shots; a 3-shot graph "
                  f"DROPS shot(s) 4+. Trim the script or wait for the "
                  f"dynamic-count workflow.", flush=True)
        while len(shots) < 4:
            shots.append(shots[-1])
        return (shots[0], shots[1], shots[2], shots[3], n)


class H3ModelLoaderAny:
    """One dropdown, both formats: .safetensors loads through comfy core,
    .gguf routes through ComfyUI-GGUF (patched for minimax_h3). Keeps the
    published workflow at exactly one loader node."""

    @classmethod
    def INPUT_TYPES(cls):
        import folder_paths
        files = folder_paths.get_filename_list("diffusion_models")
        gguf = []
        for d in folder_paths.get_folder_paths("diffusion_models"):
            import os
            if os.path.isdir(d):
                gguf += [f for f in os.listdir(d) if f.lower().endswith(".gguf")]
        names = sorted(set(files) | set(gguf))
        return {"required": {"model_name": (names, {
            "tooltip": "safetensors or GGUF - loader routes automatically."})}}

    RETURN_TYPES = ("MODEL",)
    FUNCTION = "load"
    CATEGORY = "loaders/minimax"

    def load(self, model_name):
        import folder_paths
        if model_name.lower().endswith(".gguf"):
            # resolve the live UnetLoaderGGUF from the global registry -
            # custom node packages load under mangled module names, so the
            # registry is the only stable handle.
            import nodes as core_nodes
            cls = core_nodes.NODE_CLASS_MAPPINGS.get("UnetLoaderGGUF")
            if cls is None:
                raise RuntimeError(
                    "ComfyUI-GGUF not loaded - install/enable it and restart.")
            return cls().load_unet(model_name)
        import comfy.sd
        path = folder_paths.get_full_path_or_raise("diffusion_models", model_name)
        return (comfy.sd.load_diffusion_model(path),)


class H3ClipLoaderAny:
    """One dropdown for text encoders, both formats: .safetensors through
    comfy core CLIPLoader, .gguf through ComfyUI-GGUF's CLIPLoaderGGUF
    (which auto-pairs a matching -mmproj sidecar for vision)."""

    @classmethod
    def INPUT_TYPES(cls):
        import os
        import folder_paths
        files = set(folder_paths.get_filename_list("text_encoders"))
        for d in folder_paths.get_folder_paths("text_encoders"):
            if os.path.isdir(d):
                files |= {f for f in os.listdir(d)
                          if f.lower().endswith(".gguf")
                          and "mmproj" not in f.lower()}
        import nodes as core_nodes
        types = core_nodes.CLIPLoader.INPUT_TYPES()["required"]["type"]
        return {"required": {
            "clip_name": (sorted(files), {
                "tooltip": "safetensors or GGUF - routed automatically. GGUF "
                           "encoders auto-pair their -mmproj vision sidecar."}),
            "type": types,
        }}

    RETURN_TYPES = ("CLIP",)
    FUNCTION = "load"
    CATEGORY = "loaders/minimax"

    def load(self, clip_name, type):
        import nodes as core_nodes
        if clip_name.lower().endswith(".gguf"):
            cls = core_nodes.NODE_CLASS_MAPPINGS.get("CLIPLoaderGGUF")
            if cls is None:
                raise RuntimeError(
                    "ComfyUI-GGUF not loaded - install/enable it and restart.")
            return cls().load_clip(clip_name, type)
        return core_nodes.CLIPLoader().load_clip(clip_name, type=type)


class H3AudioTrimStart:
    """Trim N seconds off the FRONT of an audio clip. Exists so the multishot
    master can drop each chained shot's duplicated first frame (1/24s) from
    video AND audio together, keeping lip sync exact across seams."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "audio": ("AUDIO",),
            "seconds": ("FLOAT", {"default": 0.04167, "min": 0.0, "max": 10.0,
                                  "step": 0.00001}),
        }}

    RETURN_TYPES = ("AUDIO",)
    FUNCTION = "trim"
    CATEGORY = "audio"

    def trim(self, audio, seconds):
        sr = audio["sample_rate"]
        wav = audio["waveform"]
        n = int(round(seconds * sr))
        return ({"sample_rate": sr, "waveform": wav[..., n:]},)


class H3MultishotSampler:
    """The whole multishot pipeline in one node: parse script, loop shots,
    chain each shot's last frame into the next shot's first_frame, seam-trim,
    and return master frames + master audio. shot_count is REAL here: N shots
    means N sampled shots, no wasted execution.

    JoyEcho architecture applied to H3: multishot complexity lives inside the
    node so the canvas stays legible."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "model": ("MODEL",),
            "clip": ("CLIP",),
            "video_vae": ("VAE",),
            "audio_vae": ("VAE",),
            "script": ("STRING", {
                "multiline": True, "dynamicPrompts": False,
                "default": "Shot 1 prompt goes here.\n---\n"
                           "Shot 2 prompt goes here.\n---\n"
                           "Shot 3 prompt goes here.",
                "tooltip": "One prompt per shot, separated by --- on its own "
                           "line. JSON {\"prompts\": [...]} also accepted."}),
            "shot_count": ("INT", {
                "default": 0, "min": 0, "max": 8,
                "tooltip": "0 = one shot per script prompt. 1-8 forces the "
                           "count: extra prompts drop, missing ones continue "
                           "the last prompt. Every shot renders - this is "
                           "the real thing here."}),
            "width": ("INT", {"default": 768, "min": 32, "max": 4096,
                              "step": 32}),
            "height": ("INT", {"default": 1344, "min": 32, "max": 4096,
                               "step": 32}),
            "frames_per_shot": ("INT", {
                "default": 243, "min": 5, "max": 481, "step": 17,
                "tooltip": "Frames at 24fps on H3's 17k+5 grid (243 = ~10.1s;"
                           " 362 = trained max ~15.1s; beyond is untested)."}),
            "seed": ("INT", {"default": 0, "min": 0,
                             "max": 0xffffffffffffffff,
                             "control_after_generate": True}),
            "steps": ("INT", {"default": 20, "min": 1, "max": 50}),
        }}

    RETURN_TYPES = ("IMAGE", "AUDIO", "INT")
    RETURN_NAMES = ("master_frames", "master_audio", "shots_rendered")
    FUNCTION = "run"
    CATEGORY = "sampling/minimax"

    def run(self, model, clip, video_vae, audio_vae, script, shot_count,
            width, height, frames_per_shot, seed, steps):
        import torch
        import node_helpers
        from comfy_extras import nodes_custom_sampler as ncs
        from comfy_extras import nodes_minimax_h3 as mmh3
        from comfy_extras.nodes_audio import vae_decode_audio

        shots = _parse_script(script)
        n = shot_count if shot_count > 0 else len(shots)
        if len(shots) > n:
            print(f"[H3Multishot] dropping {len(shots) - n} extra script "
                  f"prompt(s) (shot_count={n}).", flush=True)
            shots = shots[:n]
        while len(shots) < n:
            print(f"[H3Multishot] shot {len(shots) + 1} continues the last "
                  f"prompt (script had fewer prompts than shot_count).",
                  flush=True)
            shots.append(shots[-1])

        sigmas = ncs.BasicScheduler().get_sigmas(model, "simple", steps, 1.0)[0]
        sampler = ncs.KSamplerSelect().get_sampler("res_multistep")[0]

        frames_parts, audio_parts = [], []
        sr = None
        prev_last = None
        for si, prompt in enumerate(shots):
            print(f"[H3Multishot] shot {si + 1}/{n} "
                  f"({frames_per_shot}f @ {width}x{height})...", flush=True)
            latent, frame_count = mmh3._empty_av_latent(
                width, height, frames_per_shot)
            images, keyframes = [], []
            if prev_last is not None:
                img = mmh3._resize(prev_last[:1], width, height, "disabled")
                images.append(img)
                keyframes.append({"resolved_frame_index": 0, "image": img})
            tokens = clip.tokenize(prompt, images=images)
            cond = clip.encode_from_tokens_scheduled(tokens)
            if keyframes:
                for kf in keyframes:
                    kf["latent"] = video_vae.encode(kf.pop("image"))
                cond = node_helpers.conditioning_set_values(cond, {
                    "minimax_keyframes": keyframes,
                    "minimax_frame_count": frame_count,
                })
            guider = ncs.BasicGuider().get_guider(model, cond)[0]
            noise = ncs.RandomNoise().get_noise(seed + si)[0]
            out, _denoised = ncs.SamplerCustomAdvanced().sample(
                noise, guider, sampler, sigmas, latent)

            lat = out["samples"]
            if getattr(lat, "is_nested", False):
                lat = lat.unbind()[0]        # AV pair: [0]=video, [-1]=audio
            imgs = video_vae.decode(lat)
            if imgs.ndim == 5:
                imgs = imgs.reshape(-1, imgs.shape[-3], imgs.shape[-2],
                                    imgs.shape[-1])
            aud = vae_decode_audio(audio_vae, out)
            sr = aud["sample_rate"]
            wav = aud["waveform"]

            prev_last = imgs[-1:].clone()
            if si > 0:
                imgs = imgs[1:]                       # duplicated seam frame
                trim = int(round(sr / 24.0))          # matching 1/24s audio
                wav = wav[..., trim:]
            frames_parts.append(imgs.cpu())
            audio_parts.append(wav.cpu())

        master = torch.cat(frames_parts, dim=0)
        waveform = torch.cat(audio_parts, dim=-1)
        print(f"[H3Multishot] done: {n} shots, {master.shape[0]} frames "
              f"(~{master.shape[0] / 24.0:.1f}s).", flush=True)
        return (master, {"waveform": waveform, "sample_rate": sr}, n)


NODE_CLASS_MAPPINGS = {"H3ScriptSplit": H3ScriptSplit,
                       "H3ModelLoaderAny": H3ModelLoaderAny,
                       "H3ClipLoaderAny": H3ClipLoaderAny,
                       "H3AudioTrimStart": H3AudioTrimStart,
                       "H3MultishotSampler": H3MultishotSampler}
NODE_DISPLAY_NAME_MAPPINGS = {
    "H3ScriptSplit": "H3 Shot List",
    "H3ModelLoaderAny": "H3 Model Loader (safetensors + GGUF)",
    "H3ClipLoaderAny": "H3 CLIP Loader (safetensors + GGUF)",
    "H3AudioTrimStart": "H3 Audio Trim Start",
    "H3MultishotSampler": "H3 Multishot Sampler (one node)"}
