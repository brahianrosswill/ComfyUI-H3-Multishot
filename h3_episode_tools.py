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
    """Concatenate two video+audio segments into one continuous take.

    match_b (default on): measure the seam and match segment B's texture to
    segment A. The two-stage chain renders A on ref2va (soft - reference
    conditioning pulls the image toward the refs' texture) and B on fl2va
    (crisper, higher micro-contrast); measured on a real take the seam was a
    +119..174% Laplacian sharpness step plus +5% luma - a visible focus
    snap. Steps parity cannot equalize two checkpoints, so B gets an
    auto-tuned gaussian (sigma searched until B's Laplacian lands on A's)
    and a luma affine, in float tensors before any encode. A's softer look
    IS the intended consumer-camcorder texture, so matching downward is the
    correct direction. Skips itself when the seam is already within 15%.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images_a": ("IMAGE",), "audio_a": ("AUDIO",),
            "images_b": ("IMAGE",), "audio_b": ("AUDIO",),
        }, "optional": {
            "match_b": (["match_to_a", "off"], {"default": "match_to_a",
                "tooltip": "Match segment B's sharpness/tone to segment A "
                "at the seam (the two stages render on different "
                "checkpoints with different texture character)."}),
        }}

    RETURN_TYPES = ("IMAGE", "AUDIO")
    RETURN_NAMES = ("images", "audio")
    FUNCTION = "concat"
    CATEGORY = "video/minimax"

    @staticmethod
    def _gray(x):
        return (0.299 * x[..., 0] + 0.587 * x[..., 1] + 0.114 * x[..., 2])

    @classmethod
    def _lap_var(cls, x):
        import torch
        g = cls._gray(x).unsqueeze(1)
        k = torch.tensor([[0., 1., 0.], [1., -4., 1.], [0., 1., 0.]],
                         dtype=g.dtype, device=g.device).view(1, 1, 3, 3)
        return float(torch.nn.functional.conv2d(g, k, padding=1).var())

    @staticmethod
    def _gauss(x, sigma):
        """Separable gaussian on [T,H,W,C], returns same shape."""
        import math
        import torch
        r = max(1, int(math.ceil(3 * sigma)))
        t = torch.arange(-r, r + 1, dtype=x.dtype, device=x.device)
        k = torch.exp(-(t ** 2) / (2 * sigma * sigma))
        k = (k / k.sum()).view(1, 1, 1, -1)
        v = x.permute(0, 3, 1, 2)                       # [T,C,H,W]
        c = v.shape[1]
        kh = k.expand(c, 1, 1, k.shape[-1])
        v = torch.nn.functional.conv2d(v, kh, padding=(0, r), groups=c)
        kv = k.view(1, 1, -1, 1).expand(c, 1, k.shape[-1], 1)
        v = torch.nn.functional.conv2d(v, kv, padding=(r, 0), groups=c)
        return v.permute(0, 2, 3, 1)

    def _match(self, images_a, images_b):
        import torch
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        na = images_a[-min(24, images_a.shape[0]):].to(dev)
        step = max(1, images_b.shape[0] // 24)
        nb = images_b[::step][:24].to(dev)
        lap_a, lap_b = self._lap_var(na), self._lap_var(nb)
        ga, gb = self._gray(na), self._gray(nb)
        ma, sa = float(ga.mean()), float(ga.std())
        mb, sb = float(gb.mean()), float(gb.std())
        sigma = 0.0
        if lap_b > lap_a * 1.15:
            ref = nb[len(nb) // 2:len(nb) // 2 + 1]
            best = (float("inf"), 0.0)
            for s in (0.3, 0.45, 0.6, 0.8, 1.0, 1.3, 1.6):
                d = abs(self._lap_var(self._gauss(ref, s)) - lap_a)
                if d < best[0]:
                    best = (d, s)
            sigma = best[1]
        gain = max(0.85, min(1.15, sa / max(sb, 1e-6)))
        off = ma - mb * gain
        if sigma == 0.0 and abs(off) < 0.006 and abs(gain - 1) < 0.02:
            print(f"[H3ConcatAV] seam already matched (sharp "
                  f"{lap_b / max(lap_a, 1e-9):+.0%} vs A) - no-op", flush=True)
            return images_b
        out = torch.empty_like(images_b)
        for i in range(0, images_b.shape[0], 32):
            ch = images_b[i:i + 32].to(dev)
            if sigma > 0:
                ch = self._gauss(ch, sigma)
            ch = (ch * gain + off).clamp(0, 1)
            out[i:i + 32] = ch.to(images_b.device)
        print(f"[H3ConcatAV] matched B to A: sigma {sigma:.2f}, gain "
              f"{gain:.3f}, offset {off:+.4f} (sharp was "
              f"{lap_b / max(lap_a, 1e-9):+.0%} vs A)", flush=True)
        return out

    def concat(self, images_a, audio_a, images_b, audio_b,
               match_b="match_to_a"):
        import torch
        if tuple(images_a.shape[1:3]) != tuple(images_b.shape[1:3]):
            raise ValueError(
                f"[H3ConcatAV] frame sizes differ: A "
                f"{tuple(images_a.shape[1:3])} vs B "
                f"{tuple(images_b.shape[1:3])} - both stages must render at "
                "the same width/height.")
        if match_b == "match_to_a":
            images_b = self._match(images_a, images_b)
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


class H3RefBatch:
    """Adapt JoyEcho_RefPicker's output to MiniMaxH3ReferenceToVideo.

    The RefPicker returns one IMAGE batch (one frame per picked reference)
    plus a `picked_path` string ("path; path; ..."). H3's reference node
    wants SEPARATE ref_image_N inputs and <Picture N> identity bindings in
    the prompt. This node splits the batch into up to 9 slots, dedupes the
    re-entry duplicates the picker schedules for LTX (meaningless for
    ref2va - all refs bind at t=0), derives character names from each
    path's parent folder, and prepends the binding lines to the prompt.
    """

    MAX_SLOTS = 9

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "prompt": ("STRING", {"forceInput": True}),
        }, "optional": {
            "reference_image": ("IMAGE",),
            "picked_path": ("STRING", {"forceInput": True, "default": ""}),
        }}

    RETURN_TYPES = tuple(["IMAGE"] * 9 + ["STRING", "STRING"])
    RETURN_NAMES = tuple([f"ref_{i+1}" for i in range(9)]
                         + ["prompt_out", "report"])
    FUNCTION = "adapt"
    CATEGORY = "video/minimax"

    def adapt(self, prompt, reference_image=None, picked_path=""):
        import os
        if reference_image is None or (picked_path or "").startswith("("):
            print("[H3RefBatch] no references from picker; prompt passes "
                  "through unchanged.", flush=True)
            return tuple([None] * self.MAX_SLOTS + [prompt, "(no references)"])

        paths = [p.strip() for p in (picked_path or "").split(";") if p.strip()]
        frames = [reference_image[i:i+1] for i in range(reference_image.shape[0])]
        # dedupe the picker's re-entry duplicates (same path repeated)
        keep, seen = [], set()
        for i, fr in enumerate(frames):
            p = paths[i] if i < len(paths) else f"(slot {i})"
            if p in seen:
                continue
            seen.add(p)
            keep.append((fr, p))
        keep = keep[:self.MAX_SLOTS]

        binds, lines, per_char, order = [], [], {}, []
        for idx, (fr, p) in enumerate(keep, start=1):
            char = os.path.basename(os.path.dirname(p)) or "character"
            if char not in per_char:
                per_char[char] = []
                order.append(char)
            per_char[char].append(idx)
            lines.append(f"{char}/{os.path.basename(p)} -> <Picture {idx}>")
        for char in order:
            nums = [f"<Picture {i}>" for i in per_char[char]]
            # variant folders (zara_preflash, madison-corrupted) are the SAME
            # person - bind the base name, i.e. the first separator token
            disp = re.split(r"[-_]", char)[0].title()
            binds.append(f"{', '.join(nums)} "
                         f"{'is' if len(nums) == 1 else 'are'} "
                         f"the same person ({disp}).")

        prompt_out = "\n".join(binds) + "\n" + (prompt or "")
        report = f"{len(keep)} ref(s): " + "; ".join(lines)
        print(f"[H3RefBatch] {report}", flush=True)
        out = [fr for fr, _ in keep] + [None] * (self.MAX_SLOTS - len(keep))
        return tuple(out + [prompt_out, report])


NODE_CLASS_MAPPINGS = {
    "H3EpisodeSplit": H3EpisodeSplit,
    "H3LastFrame": H3LastFrame,
    "H3ConcatAV": H3ConcatAV,
    "H3AutoRefs": H3AutoRefs,
    "H3RefBatch": H3RefBatch,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "H3EpisodeSplit": "H3 Episode Split (stage A + B)",
    "H3LastFrame": "H3 Last Frame",
    "H3ConcatAV": "H3 Concat A/V",
    "H3AutoRefs": "H3 Auto Refs (folders, by prompt)",
    "H3RefBatch": "H3 Ref Batch (RefPicker -> ref slots)",
}
