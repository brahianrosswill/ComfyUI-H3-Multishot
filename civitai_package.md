# Civitai page draft — HOLD until Joe's publish go

**Type:** Workflows (attach H3_Multishot_AIO.json + H3_Multishot_3chain_expert.json)
**Title:** MiniMax-H3 Multishot — chained shots, one master, GGUF support
**Tags:** minimax-h3, video, audio, multishot, gguf, comfyui, found footage

---

Chain multiple MiniMax-H3 shots into one continuous video **with audio** — in
one node.

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

Roadmap: ref2va hard mode — identity from reference images and **voice
clips**, held across every shot.

---
*(Sample videos: attach the WITNESS master + one single-shot clip once
picked. Cover image: frame from shot 2 corridor.)*
