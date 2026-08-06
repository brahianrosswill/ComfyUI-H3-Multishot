---
license: mit
base_model: MiniMaxAI/MiniMax-H3
tags:
- comfyui
- workflow
- video
- audio
- text-to-video
- minimax-h3
- multishot
---

# MiniMax-H3 Multishot Workflow

**v1.4** — `sampler_name` and `scheduler` are now widgets on both multishot
samplers (defaults `res_multistep` / `simple`, exactly the values previously
hardcoded, so existing workflows render identically). The bundled workflows are
relabelled: every node carries a descriptive title. Node pack:
[ComfyUI-H3-Multishot v1.4](https://github.com/jlucasmcrell/ComfyUI-H3-Multishot).


Chain multiple MiniMax-H3 shots into one continuous video **with audio** - in
one node. Each shot starts from the last frame of the previous one; the
duplicated seam frame and its 1/24s of audio are trimmed automatically.

The demo below was made **by this workflow**: 30 seconds, three chained shots
from one script, same presenter and same voice across both seams, rendered on
the Q5_1 GGUF.

<video controls src="https://huggingface.co/joeygambino/MiniMax-H3-Multishot-Workflow/resolve/main/H3_multishot_presenter_demo.mp4"></video>

## Files

- **H3_Multishot_AIO.json** - easy mode: loaders > script box > one sampler
  node > save. Write one prompt per shot with `---` between them, pick a
  shot count (0 = one shot per prompt, 1-8 forces it), queue.
- **H3_Multishot_3chain_expert.json** - the same pipeline exploded into three
  visible shot chains for per-stage tinkering.

## Requirements

- ComfyUI **v0.30.0+** (native MiniMax H3 support)
- The node pack: [ComfyUI-H3-Multishot](https://github.com/jlucasmcrell/ComfyUI-H3-Multishot) (Manager > Install via Git URL;
  includes the one-line ComfyUI-GGUF architecture patch)
- Models: [MiniMax-H3 GGUF quants](https://huggingface.co/joeygambino/MiniMax-H3-GGUF) (Q5_1 for 24-32 GB cards, Q4_0
  for 16 GB) or the originals; text encoder + VAEs from
  [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3)

## Notes

- `frames_per_shot` sits on H3's 17k+5 frame grid (243 = ~10.1s at 24 fps;
  362 = ~15.1s, the trained max).
- End every shot on what the NEXT shot expects to see - the chain hands each
  shot the previous final frame, and matching that bridge to the next shot's
  framing is what makes seams invisible.
- Malformed JSON scripts fail loudly instead of rendering the raw text.
