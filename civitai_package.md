# Civitai page draft — v1.1

**Type:** Workflows (attach H3_Multishot_AIO.json + H3_Multishot_3chain_expert.json)
**Title:** MiniMax-H3 Multishot — chained shots, one master, GGUF support
**Version:** 1.1 (image-to-video + 4x VRAM fix)
**Tags:** minimax-h3, video, audio, multishot, gguf, comfyui, found footage

---

Chain multiple MiniMax-H3 shots into one continuous video **with audio** — in
one node.

### What's new in v1.1
- **Image-to-video.** The sampler takes an optional `start_image` — connect a
  LoadImage and shot 1 begins from your frame, then chains as usual. Leave it
  unconnected and nothing changes, so v1.0 graphs still work.
- **~4x faster on 32GB cards.** The text encoder is now evicted before
  sampling. The Qwen3-VL encoder (~16.5GB) and the H3 DiT (~25GB) don't co-fit
  on 32GB, so the DiT used to load *partially* and stream ~19GB from system RAM
  every step. Measured on a 5090: **~60 min -> ~15 min** for the same render.
- **Text encoder GGUF published**, including the **mmproj** vision sidecar that
  multi-shot actually requires:
  huggingface.co/joeygambino/MiniMax-H3-encoder-GGUF

**What you get**
- The **H3 Multishot Sampler**: paste a script (one prompt per shot, `---`
  between them), pick a shot count, get a seam-clean master with continuous
  audio. Each shot starts from the last frame of the previous one.
- A **dual-format loader** — same dropdown loads .safetensors or .gguf.
- **GGUF quants** for 16-32GB cards (Q5_1 / Q4_0, both DiT flavors):
  huggingface.co/joeygambino/MiniMax-H3-GGUF — including the explanation of
  why K-quants can't exist for this model.
- An **expert workflow** with the three shot chains exploded onto the canvas
  for people who want per-stage control.

**Requirements:** ComfyUI 0.30.0+, the node pack
(github.com/jlucasmcrell/ComfyUI-H3-Multishot), ComfyUI-GGUF + the included
one-line patch for GGUF models. Text encoder/VAEs from Comfy-Org/MiniMax-H3.

**Numbers that matter:** shots live on H3's 17k+5 frame grid (243 frames ≈
10s; 362 ≈ 15s = trained max). An RTX 5090 renders a 243-frame 544x960 shot
in ~10 minutes on Q5_1. 16GB cards run Q4_0 with automatic streaming.

**Tip from testing:** render at H3's native resolution and upscale afterwards.
Rendering natively at 1920x1088 scored *worse* than 960x544 in blind review
(softer, reads as an upscale) and cost ~4x the time.

Roadmap: ref2va hard mode — identity from reference images and **voice
clips**, plus deeper multi-frame memory for long-form chains.

---
*(Sample videos: attach the WITNESS master + one single-shot clip once
picked. Cover image: frame from shot 2 corridor.)*
