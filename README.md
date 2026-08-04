# ComfyUI-H3-Multishot

Multishot video+audio generation for **MiniMax-H3** in ComfyUI: one script,
N chained shots, one seam-clean master. Plus a dual-format model loader
(safetensors + GGUF) and the GGUF architecture patch H3 needs.

## Nodes

- **H3 Multishot Sampler (one node)** - the whole pipeline: paste a script
  (one prompt per shot, `---` between shots; JSON `{"prompts": [...]}` also
  accepted), set `shot_count` (0 = one shot per prompt, 1-8 forces it), and
  get master frames + master audio out. Each shot chains from the last frame
  of the previous one; the duplicated seam frame and its 1/24s of audio are
  trimmed automatically.
- **H3 Model Loader (safetensors + GGUF)** - one dropdown for both formats.
  GGUF files route through ComfyUI-GGUF automatically.
- **H3 Shot List** - the same script parser as separate STRING outputs, for
  the expert graph.
- **H3 Audio Trim Start** - trim N seconds from the front of an AUDIO clip
  (seam-sync helper for hand-built chains).

## Install

1. Clone into `custom_nodes/` (or install via ComfyUI-Manager > Install via
   Git URL).
2. For GGUF models: install [ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF),
   then run `python apply_gguf_arch_patch.py` from this folder (one line,
   idempotent - teaches it the `minimax_h3` architecture).
3. Restart ComfyUI, load `workflows/H3_Multishot_AIO.json`.

Requires ComfyUI **v0.30.0+** (native MiniMax H3 support).

## Models

GGUF quants (Q5_1 for 24-32GB cards, Q4_0 for 16GB):
**huggingface.co/joeygambino/MiniMax-H3-GGUF** - the card there also
documents why K-quants (Q6_K etc.) are impossible for this architecture.
Text encoder + VAEs: [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3).

## Workflows

- `H3_Multishot_AIO.json` - easy mode: loaders > script > one sampler > save.
- `H3_Multishot_3chain_expert.json` - the same pipeline exploded into three
  visible shot chains for tinkering (fixed 3 shots, per-stage access).

## Notes

- `frames_per_shot` sits on H3's 17k+5 frame grid (243 = ~10.1s at 24fps;
  362 = ~15.1s, the trained max - beyond is untested but functional).
- Malformed JSON scripts fail loudly instead of rendering the raw text.
- Roadmap: ref2va reference conditioning (identity images + voice clips)
  in a hard-mode sampler.
