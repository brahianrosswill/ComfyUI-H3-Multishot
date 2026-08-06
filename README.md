# ComfyUI-H3-Multishot

Multishot video+audio generation for **MiniMax-H3** in ComfyUI: one script,
N chained shots, one seam-clean master. Plus a dual-format model loader
(safetensors + GGUF) and the GGUF architecture patch H3 needs.

**v1.5** - chained Hard Mode: one script where shot 1 renders from
references (ref2va) and later shots chain I2V from its last frame, joined
in-graph into one master with audio. Plus a 4-slot MODEL-only LoRA stack,
an `activation_reserve_gb` override on the loader for 24 GB cards, and an
experimental fix that lets references and keyframes coexist.
See [Changelog](#changelog).

## Nodes

- **H3 Keyframes (any position)** - anchor images anywhere in the clip, not
  just the first and last frame. Stock ComfyUI raises `only first/last keyframe
  anchors are supported`; that is a positional-maths limit, not a model limit
  (see the changelog). Six anchor slots plus an unbounded `images_batch`, each
  positioned as a percentage (`0%, 50%, 100%`), an absolute frame index (`0, 121,
  242`), or an inclusive range (`0-9, 352-361`). A descending range such as
  `30%-20%` reverses that section of the batch.
- **H3 Condition Strength** - how strongly keyframe/reference conditioning is
  trusted. Exposes `minimax_visual_cond_noise_aug` and
  `minimax_audio_cond_noise_aug`, which ComfyUI core reads but no stock node
  writes, so they were pinned at their defaults.
- **H3 Reference Audio (stereo guard)** - forces a reference clip to stereo
  32 kHz. A **mono** reference crashes the sampler with an unhelpful shape
  mismatch, because the layout reserves two channels and nothing in stock
  converts them.

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
- `H3_Keyframes.json` - **keyframes anywhere**, single pass. One generation,
  so the audio is one continuous stream with no seams.

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

### v1.5

- **Chained Hard Mode** (`workflows/H3_HardMode_Chained.json` + the Hard Mode
  release page): `H3EpisodeSplit` splits a `---` script into shot 1 (with your
  `<Picture N>` bindings) and the rest; shot 1 renders ref2va, `H3LastFrame`
  hands its final frame to the multishot sampler as `start_image`, and
  `H3ConcatAV` joins both segments into one master with audio.
- **`H3LoraStack`** - four MODEL-only LoRA slots (no CLIP input; H3's encoder
  is not a CLIP), `None`-inert, for e.g. 4-step turbo distills.
- **`activation_reserve_gb`** on `H3ModelLoaderAny` - override ComfyUI's very
  conservative inference-memory estimate (at 736x1344x362f it reserves ~20 GB
  and streams every weight from RAM on a 24 GB card). Set a measured value
  (~6 GB) to reclaim the difference for resident weights. Survives LoRA
  stacks cloning the patcher.
- **Experimental: references + keyframes can coexist** - core ComfyUI drops
  keyframe latents when references are present (an overwrite where an append
  belongs), which is the real cause of the long-standing "no refs + start
  frame" limitation. The pack now merges them in the correct packed order,
  and `H3KeyframeInject` adds a start-frame keyframe to ref2va conditioning.
  Measured: the ref2va checkpoint follows the keyframe's subjects and staging
  but holds it match-cut tight, not pixel tight - treat chains built this way
  as cuts, not continuous takes.
- Auto-reference helpers (`H3AutoRefs`, `H3RefBatch`): pick per-character
  reference sets from folders by scanning the prompt's prose (dialogue
  stripped), and generate the `<Picture N>` binding lines automatically.

### v1.4

- **`sampler_name` and `scheduler` are widgets on both multishot samplers.**
  They were hardcoded to `res_multistep` / `simple` internally; those are now
  the defaults, so an existing workflow renders exactly what it rendered
  before. The option lists come from `comfy.samplers.KSampler` at call time
  (44 samplers, 9 schedulers on current ComfyUI) rather than a copy that can
  go stale.

  The new widgets sit at the END of the optional inputs on purpose: ComfyUI
  serialises widget values positionally, so inserting them earlier would
  silently re-map the saved settings of every existing workflow.

- **Bundled workflows relabelled.** Every node in the three graphs now carries
  a descriptive title (the two bare `VAELoader`s are "Video VAE" / "Audio VAE",
  the reference slots state their `<Picture n>` binding, and the long-form
  graph's read-me note no longer sits on top of the model loaders).

### v1.3

- **Keyframe positions take percentages and ranges.** Contributed by
  [@viralesveras](https://github.com/viralesveras) in
  [#4](https://github.com/jlucasmcrell/ComfyUI-H3-Multishot/pull/4). Previously a
  bare `1` meant *the last frame*, not frame 1, so addressing an early frame
  absolutely required writing `1.0001` - which is how the ambiguity was found.

      0%, 50%, 100%     percentages
      0, 121, 242       absolute frame indices
      0-9, 352-361      inclusive ranges
      30%-20%           descending: reverses that section of the batch

  **Existing workflows keep working.** A bare non-integer at or below 1.0 is
  unambiguous - nobody means "frame index 0.5" - so a plain list containing one
  is read the old way and logs the percentage spelling to switch to. An
  all-integer `0, 1` is genuinely ambiguous, so it takes the new absolute meaning
  and warns rather than silently anchoring a different frame.
- **`images_batch` on the keyframe node.** Also from @viralesveras, in
  [#2](https://github.com/jlucasmcrell/ComfyUI-H3-Multishot/pull/2), for when six
  slots is not enough - several frames at each end to pin complex motion, or a
  set of frames kept from a source video. It **adds to** the six individual
  slots; as originally merged it replaced them, which silently dropped `image_1`.
- **Loaders find GGUFs in subfolders.** Both model loaders scanned only the top
  level of `diffusion_models` / `text_encoders`, so a file under `gguf/` was
  invisible in the dropdown while ComfyUI-GGUF's own loader listed it fine. The
  scan exists because `.gguf` is not in `supported_pt_extensions`; it simply was
  not recursive.

### v1.2

- **Keyframes at any position.** Stock ComfyUI pins H3 keyframes to frame 0 and
  frame N-1 and raises `only first/last keyframe anchors are supported` for
  anything else. Both stock cases are actually the same expression, because
  `sum(_video_t_spans(latent_t)) == FRAME_RESCALE * frame_count`:

  ```
  cond_t = text_len + FRAME_RESCALE * pixel_index
  ```

  which is defined for every frame, not just the two endpoints.

  Measured on an RTX 5090, 243 frames, one anchor at pixel frame 121: the
  rendered frame most resembling the anchor image was frame **122** - the
  requested position, off by one - reached by continuous motion with no cut
  (peak frame-to-frame change 2.3x median), audio unbroken through it.

  The patch is applied **in memory**; it does not edit any ComfyUI file. It
  self-tests against the stock formula before committing and rolls itself back
  if first/last positions do not reproduce exactly, so a future ComfyUI change
  degrades to "interior anchors unavailable" rather than to broken renders.

  **Move vs cut.** Anchor images with a plausible camera path between them
  (same place, different angle) make H3 interpolate. Images with no possible
  path (a kitchen and a diner) make it **cut**, then hold - stock first/last
  does exactly the same with such a pair, so that is the model being sensible,
  not a defect. The cut case has its own use: a timed shot change inside ONE
  generation, which keeps the audio continuous across it.

- **Reference-to-video groundwork.** The stereo guard and strength control
  below are what reference workflows need. The hard-mode graph itself is
  built but has not been rendered yet, so it is not in this release.

  **References and keyframes cannot coexist.** This is core behaviour, not a
  choice here: `model_base.py` *assigns* `cond_video_latents` for refs,
  discarding keyframe latents while the keyframe layout rows survive, and the
  packed sequence then desyncs into a shape-mismatch crash. Pick one per shot.

  Reference tags are **1-based** in the prompt (`<Picture 1>`) while the input
  slots are **0-based** (`ref_image_0`). A reference video *with* a soundtrack
  also consumes an `<Audio j>` ordinal before your standalone clips.

- **H3 Reference Audio (stereo guard).** Mono reference audio produced half the
  rows the layout reserved and died deep inside the model. Now handled.

- **H3 Condition Strength.** `minimax_visual_cond_noise_aug` /
  `minimax_audio_cond_noise_aug` are read by core and written by nothing, so
  they sat at 0.999 / 1.0 forever. They blend noise into conditioning latents
  and set the timestep the condition rows occupy - an anchor-strength dial.

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

## On Civitai

- [MiniMax-H3 Multishot (workflows)](https://civitai.com/models/2833322)
- [MiniMax-H3 GGUF - the DiT](https://civitai.com/models/2833352)
- [MiniMax-H3 Text Encoder GGUF](https://civitai.com/models/2834385)
