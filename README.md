# ComfyUI-H3-Multishot

Multishot video+audio generation for **MiniMax-H3** in ComfyUI: one script,
N chained shots, one seam-clean master. Plus a dual-format model loader
(safetensors + GGUF) and the GGUF architecture patch H3 needs.

**v1.1** - image-to-video start frame, and a VRAM fix that cuts render time
roughly 4x on 32GB cards. See [Changelog](#changelog).

## Nodes

- **H3 Multishot Sampler (one node)** - the whole pipeline: paste a script
  (one prompt per shot, `---` between shots; JSON `{"prompts": [...]}` also
  accepted), set `shot_count` (0 = one shot per prompt, 1-8 forces it), and
  get master frames + master audio out. Each shot chains from the last frame
  of the previous one; the duplicated seam frame and its 1/24s of audio are
  trimmed automatically.
  - **`start_image` (optional, v1.1)** - connect a `LoadImage` and shot 1
    starts from that frame (image-to-video). Leave it unconnected for pure
    text-to-video; behaviour is unchanged. Shot 1 keeps its first frame (no
    seam trim), so the image you supply is the image you get.
- **H3 Model Loader (safetensors + GGUF)** - one dropdown for both formats.
  GGUF files route through ComfyUI-GGUF automatically.
- **H3 CLIP Loader (safetensors + GGUF)** - the same treatment for text
  encoders; GGUF encoders auto-pair their `-mmproj` vision sidecar so image
  referencing keeps working.
- **H3 Shot List** - the same script parser as separate STRING outputs, for
  the expert graph.
- **H3 Multishot Sampler + Memory (long form)** - for 2-5 minute videos
  (12-30 shots) where plain chaining drifts. Stock chaining shows each shot ONE
  image (the previous shot's last frame), so every hop can only see one hop
  back and identity error compounds. This node splits the two jobs:
  the **keyframe** stays the most recent frame (seams stay smooth), while the
  **memory** shown to the encoder is a persistent **anchor** from the start of
  the piece plus the last N shot-end frames. The anchor never changes, so drift
  cannot compound. Knobs: `anchor_frames` (1 = on, the long-chain fix) and
  `memory_frames` (recent frames, 0 = stock behaviour).
- **H3 Optional Image (I2V on/off)** - a real toggle for an optional image
  input. A normal switch node cannot express "no image" (both branches are
  required), so turning I2V off usually ends up feeding a black placeholder
  frame - which is not text-to-video, it is video that starts from black. This
  node emits nothing when disabled.
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
[**joeygambino/MiniMax-H3-GGUF**](https://huggingface.co/joeygambino/MiniMax-H3-GGUF) - the card there also
documents why K-quants (Q6_K etc.) are impossible for this architecture.
Workflows also live on HF: [MiniMax-H3-Multishot-Workflow](https://huggingface.co/joeygambino/MiniMax-H3-Multishot-Workflow).
Text encoder GGUF + **the required mmproj vision sidecar**:
[**joeygambino/MiniMax-H3-encoder-GGUF**](https://huggingface.co/joeygambino/MiniMax-H3-encoder-GGUF).
The mmproj is not optional if you use reference images **or more than one
shot** - shot chaining feeds the previous shot's last frame through the
encoder's vision path.

Full-precision text encoder + VAEs: [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3).

## Workflows

- `H3_Multishot_AIO.json` - easy mode: loaders > script > one sampler > save.
  Ships with a `LoadImage` -> **H3 Optional Image** -> `start_image` chain, so
  the same graph does T2V and I2V: flip the toggle on to use your frame.
- `H3_Multishot_MEMORY.json` - long-form mode: the memory sampler with an
  identity anchor, for 2-5 minute multi-shot pieces.
- `H3_Multishot_3chain_expert.json` - the same pipeline exploded into three
  visible shot chains for tinkering (fixed 3 shots, per-stage access).

## Sample

[`samples/H3_multishot_presenter_demo.mp4`](samples/H3_multishot_presenter_demo.mp4) -
30s, three chained shots from one script on the Q5_1 GGUF: identity and voice
held across both seams. This video was made BY the workflow it demonstrates.

## Notes

- `frames_per_shot` sits on H3's 17k+5 frame grid (243 = ~10.1s at 24fps;
  362 = ~15.1s, the trained max - beyond is untested but functional).
- Malformed JSON scripts fail loudly instead of rendering the raw text.
- **Resolution:** H3 is happiest at its native size. Rendering natively at
  1920x1088 measured *worse* than 960x544 in blind review (softer detail, and
  it reads as an upscale) while costing ~4x the time. Render native, then
  upscale in pixel space.
- Roadmap: ref2va reference conditioning (identity images + voice clips) and a
  deeper multi-frame memory for long-form chains, in a hard-mode sampler.

## Changelog

### v1.1
- **Image-to-video.** New optional `start_image` input on the Multishot
  Sampler. Shot 1 uses it as its keyframe, the same way later shots use the
  previous shot's last frame. Unconnected = unchanged T2V behaviour, so
  existing graphs keep working.
- **VRAM fix: the text encoder is now evicted before sampling.** The Qwen3-VL
  encoder (~16.5GB even at Q4) and the H3 DiT (~25GB) do not co-fit on a 32GB
  card. Previously the DiT loaded *partially* and streamed ~19GB from system
  RAM on every step:

  ```
  loaded partially; 6423 MB usable, 5847 MB loaded, 19363 MB offloaded
  ```

  Conditioning is already computed before sampling starts, so the encoder is
  safe to evict there. Measured on an RTX 5090: **~60 min -> ~15 min** for the
  same render. The node prints `[H3Multishot] TE evicted; NN.N GB free for the
  DiT` each shot so you can confirm it. The encoder reloads per shot (a few
  seconds) because chained prompts need it again - far cheaper than streaming.
- **Long-form memory sampler (new node).** `H3 Multishot Sampler + Memory`
  adds a persistent identity anchor plus rolling recent-frame memory, aimed at
  12-30 shot (2-5 minute) chains where single-frame chaining drifts.
- **H3 Optional Image (new node).** A genuine on/off for optional image inputs;
  emits nothing when disabled instead of a placeholder frame.
- **Script parser now self-repairs.** Long JSON scripts that lose their closing
  brace/bracket, end on a trailing comma, or have an unterminated string are
  auto-closed with a console warning instead of failing the render. Genuinely
  malformed scripts still fail loudly.
- Docs: linked the encoder GGUF repo and spelled out that **mmproj is required
  for multi-shot**, not just for reference images.

### v1.0
- Initial release: multishot sampler, dual-format model/CLIP loaders, shot
  list, audio trim, GGUF arch patch, AIO + 3-chain expert workflows.

## Support

Everything here is free and stays free - the format spec, the nodes, the
workflows, the cartridges, the LoRAs. If it saved you a night of debugging (it
contains several hundred of mine), tips keep the 5090 warm:

* [Buy me a coffee on Ko-fi](https://ko-fi.com/joeygambino)
* [Sponsor on GitHub](https://github.com/sponsors/jlucasmcrell)
* [Liberapay](https://liberapay.com/joeygambino) (recurring)
