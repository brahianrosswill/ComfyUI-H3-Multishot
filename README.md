# ComfyUI-H3-Multishot

**Render a multi-shot MiniMax-H3 scene as one continuous take: no visible cuts, no colour shift between shots, unbroken audio.**

MiniMax-H3 natively generates blocks of roughly 10-15 seconds. This pack chains those blocks into a scene of arbitrary length and joins them so the result reads as a single unedited camera take rather than a cut sequence. It ships two independent chaining mechanisms, a complete single-purpose workflow (plus a variant with zero third-party dependencies), a dual-format model loader (safetensors + GGUF), and the GGUF architecture patch H3 needs.

Current release: **v2.0 - MiniMax-H3 Seamless Chain**.

- GitHub: <https://github.com/jlucasmcrell/ComfyUI-H3-Multishot>
- Civitai: <https://civitai.com/models/2833322>

---


### Nodes added in 2.1

| Node | What it does |
|---|---|
| `RiftPromptSource` | One dropdown over LPFF-style `.txt` briefs and passthrough `.json` scripts. Emits `story_idea` / `character` / `count`. Reads `input/rift_prompts/`, and still reads the older `input/joyecho_prompts/` so existing folders keep working. |
| `RiftScriptPicker` | JSON script dropdown, and the speaker/voice stash `RiftPromptSource` feeds. |
| *(not a node)* `unload_model_after` | A switch **added to the LLM prompt writer** (`JoyEcho_LLMEnhance`). On, the writer frees its own model from Ollama once the script is written, so the video model gets the card. Uses the writer's existing `base_url` and `model_name` — nothing to keep in sync. Added in memory at startup by this pack, so the writer's own package is not modified; the switch simply appears on the node. Off by default. Ollama's OpenAI-compatible endpoint has no `keep_alive` field and its shim never sets one, so without this the model sits for the server default of five minutes — your whole first shot. |

`JoyEcho_PromptSource` and `JoyEcho_ScriptPicker` still resolve as deprecated
aliases, so graphs saved against 2.0 open unchanged. They were never published
under those names — that was the 2.0 bug.

### The prompt writer needs a model you actually have

The full workflow points at a local Ollama with `model_name = qwen3:14b`.
**Pull it before the first queue** or the run stops with
`LLM API error 404: model 'qwen3:14b' not found`:

```
ollama pull qwen3:14b
```

Any OpenAI-compatible endpoint works — its URL in `base_url`, its exact tag in
`model_name` (`ollama list` prints the tags you have). A remote endpoint is
often better: a local writer large enough to be good competes with H3 for the
same card and on under 32 GB will evict the model mid-render. When you do run
local, turn on `unload_model_after` on the writer — it frees the model as soon
as the script is written.

No LLM at all? Set `use_file_prompts` to manual entry, delete the writer, and
feed your own `---`-separated shot script into the sampler's `script` input.
The CORE workflow already works this way.

**Try a render with every switch off and the reserve at `0` before touching
any of this.** The activation reserve measures each shape and conditioning
payload as it renders and sizes the pool itself, and it holds on 24 GB cards
as well as 32 GB. A hand-set reserve *overrides* that measurement. These
switches are for digging out of a spill the console has already named.

## Quick start

Five steps to a rendering chain. This path uses the **CORE** workflow, which needs nothing except this pack and ComfyUI built-ins.

**1. Install the node pack**

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/jlucasmcrell/ComfyUI-H3-Multishot
```

Or in ComfyUI-Manager: *Install via Git URL*. Requires **ComfyUI v0.30.0+** (native MiniMax-H3 support).

**2. Put the models in place**

```
ComfyUI/models/diffusion_models/   <- MiniMax-H3 ref2va checkpoint (safetensors or GGUF)
ComfyUI/models/text_encoders/      <- H3 text encoder (+ its -mmproj sidecar if GGUF)
ComfyUI/models/vae/                <- video VAE + audio VAE
```

Download links are in [Models](#models).

**3. Restart ComfyUI and load the workflow**

```
MiniMax-H3_Seamless_Chain_v2.0.zip
ComfyUI-H3-Multishot/LICENSE
ComfyUI-H3-Multishot/README.md
ComfyUI-H3-Multishot/__init__.py               defensive loader
ComfyUI-H3-Multishot/apply_gguf_arch_patch.py  on-disk GGUF arch fallback
ComfyUI-H3-Multishot/h3_advanced.py            advanced sampling helpers
ComfyUI-H3-Multishot/h3_avbank_probe.py        AV bank diagnostics
ComfyUI-H3-Multishot/h3_cartridge.py           portable character cartridges
ComfyUI-H3-Multishot/h3_episode_tools.py       StudioControls, StudioSwitches, AnySwitch
ComfyUI-H3-Multishot/h3_gguf_arch.py           teaches ComfyUI-GGUF the minimax_h3 arch
ComfyUI-H3-Multishot/h3_interior_patch.py      interior anchors (stands down for Motion Context)
ComfyUI-H3-Multishot/h3_keyframes.py           keyframe anchor nodes
ComfyUI-H3-Multishot/h3_lora_stack.py          H3LoraStack
ComfyUI-H3-Multishot/h3_multishot_utils.py     samplers, loaders, gates
ComfyUI-H3-Multishot/h3_ref_folder.py          reference-folder picker
INSTALL.md
PROMPTING.md
SETTINGS.md
example_script.txt                             worked four-shot two-hander
workflows/H3_Keyframes.json                    single-clip keyframe anchoring
workflows/H3_Seamless_Chain_CORE.json          same job, zero third-party packs
workflows/H3_Seamless_Chain_v2.json            everything, optional lanes gated off
```

**4. Fill in the two panels**

- **MASTER CONTROLS** - resolution, frames per shot, steps. The shipped values (`1280x736`, `362`, `14`) are the verified recipe; leave them alone for your first render.
- **Script** - one prompt per shot, `---` between shots. Read [Prompting and boundary rules](#prompting-and-boundary-rules) before you write it; the join rules are the difference between a seamless take and a chain with clipped words at every seam.

**5. Queue**

`preview_first_shot` is ON by default, so shot 1 surfaces as soon as it is done and you can judge framing and voice before the rest of the chain commits. Output lands in:

```

**Three workflows, one reason each.** `v2` is everything with the optional
lanes gated off. `CORE` does the same job with zero third-party packs — start
there if you want a render before installing anything else. `Keyframes` is a
different job: a hand-built sampling graph for anchoring a single clip at
chosen frame positions with per-anchor condition strength, not multishot.

`H3_Multishot_AIO` and `H3_Multishot_MEMORY` from earlier versions are retired
— every lane they had is in v2 (the AIO's episode source, plate chain and audio
spine were folded in; MEMORY had nothing v2 lacks). Existing copies keep
working.

output/video/H3CHAIN/
```

as a 24fps video with a paired audio file.

**Then, for the FULL workflow** (`H3_Seamless_Chain_v2.json`), install the packs
it needs — ComfyUI validates **every** node class in a graph before it will
queue, so a missing pack stops the whole workflow, not just its own feature:

| Pack | Needed for |
| --- | --- |
| `ComfyUI_JoyAI_Echo_GGUF_Nodes` | the LLM prompt writer — **ships in this repo's release zip**, modified with attribution (see its NOTICE). Use that copy, not upstream: the workflow drives inputs upstream does not have. |
| [ComfyUI-H3-Motion-Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context) | `continuity=context_pin`, the shipped default |
| [RES4LYF](https://github.com/ClownsharkBatwing/RES4LYF) | the `beta57` scheduler the full workflow ships with |
| ComfyUI-sol-attn + comfyui-minimax-h3-blockcache-T8 | the VRAM/SPEED patch switches |
| [ComfyUI-Custom-Scripts](https://github.com/pythongosssss/ComfyUI-Custom-Scripts) | the on-canvas script preview |

Every one of them can be removed instead — `INSTALL.md` in the zip gives the
one-widget change or node deletion for each. Highlights: no RES4LYF → set
`scheduler` to `beta` (measured cost: lip-sync 8/10 vs 10/10, all else equal);
no Motion-Context → `continuity=first_frame`.

---

## Fixed in v2.1.1

- **`context_pin` + Motion-Context coexistence.** Both packs patched
  `MiniMaxH3.extra_conds` and Motion-Context refuses to stack on an unknown
  wrapper, so with both installed `context_pin` errored out. This pack's
  wrapper is now a superset of theirs and declares their compatibility marker
  (`_h3_motion_context_payload_patch`), so whichever loads first owns the site
  and the other stands down. Load order no longer matters.
- **`seamless_tail` fails fast.** It needs interior keyframe anchors, which
  conflict with Motion-Context; it used to crash *mid-chain* after shot 1 had
  already rendered. It now stops before any sampling with the alternatives
  named (`context_pin`, `first_frame`, or remove that pack).
- **`seamless` is labeled the legacy soft pin it is.** Latent-only, no vision
  tokens, often still reads as a cut. Use `context_pin` or `first_frame` for a
  real join.
- The dev-machine blind spot that hid the first two (an install-layout bug in
  the conflict detection) is fixed, and releases are now tested on a packaged
  clean install.

## What is new in v2.0

- **A complete single-purpose workflow.** `H3_Seamless_Chain_v2.json` - 42 nodes in 9 grouped lanes with 8 on-canvas notes - built for one job instead of exposing every knob in the pack. `H3_Seamless_Chain_CORE.json` is the same graph with every third-party node removed.
- **MASTER CONTROLS panel** (`H3StudioControls`). One node drives resolution, frames per shot and steps for the sampler *and* for the prompt writer's dialogue pacing, so the writer's line lengths stay inside the shot length you actually set.
- **VRAM/SPEED panel** (`H3StudioSwitches` plus a reserve control). Three lazily gated model patches: memory-efficient attention, chunked feed-forward, block cache. **All OFF by default reproduces the verified recipe exactly**, and the gates are lazy, so an OFF patch never executes.
- **Energy-aware seam audio ("smart weld").** The boundary audio cut now lands in the quietest gap inside the incoming shot's first 0.75s rather than blindly at sample 0. A word placed at a shot head is no longer clipped.
- **Rewritten activation-reserve heuristic.** Cache keys now include a conditioning-*payload* signature (keyframes, audio references, two-pass), so a bare shot 1 and a reference-laden shot 2 get their own memory measurements instead of sharing one. Measured pools are no longer overridden by a fixed floor, a first run of a new payload variant estimates from a measured sibling, and **a VRAM spill into system RAM is now detected and named in the console** - previously it presented only as an unexplained ~5x slowdown.
- **`join_style` on the prompt writer.** Appends the render-verified boundary rules to the system prompt so generated scripts obey them automatically.
- **`flf_chain` fails loudly.** Selecting it with no boundary plates raises a clear error instead of silently rendering an unanchored chain.

---

## Requirements

### Required

| Component | Version | Why |
| --- | --- | --- |
| ComfyUI | **v0.30.0+** | Native MiniMax-H3 support. Older builds do not have the model. |
| This pack | v2.0 | Samplers, loaders, studio controls, gates. |
| MiniMax-H3 checkpoint (`ref2va` shipped, `fl2va` also works) | - | The generator. See [Models](#models). |
| H3 text encoder + video VAE + audio VAE | - | See [Models](#models). |

The **CORE** workflow needs nothing beyond the above. It is built entirely from this pack plus ComfyUI built-ins (`LoadImage`, `LoadAudio`, `SaveVideo`, `SaveAudio`, `CreateVideo`, `VAELoader`, `PrimitiveFloat`, `Note`).

### Full workflow

These serve the **FULL** workflow. A missing one does not degrade a single
feature — ComfyUI refuses to queue a graph containing any unknown node class,
so the workflow will not run until the pack is installed **or its nodes are
removed** (each has a documented removal, see `INSTALL.md`).

| Pack | Author | Unlocks | Needed when |
| --- | --- | --- | --- |
| [ComfyUI-H3-Motion-Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context) | NikoDemon80 | `continuity=context_pin`, the raw-latent join (the shipped default) | Remove by setting `continuity=first_frame`. |
| [RES4LYF](https://github.com/ClownsharkBatwing/RES4LYF) | ClownsharkBatwing | the `beta57` scheduler | Remove by setting `scheduler=beta` (CORE ships `beta` already). |
| ComfyUI_JoyAI_Echo_GGUF_Nodes (`JoyEcho_LLMEnhance`) | RealRebelAI (modified copy in the release zip) | The automatic prompt-writing lane | Use the zip's copy. Hand-written scripts can delete the writer instead. |
| [ComfyUI-Custom-Scripts](https://github.com/pythongosssss/ComfyUI-Custom-Scripts) | pythongosssss | `ShowText` script preview on canvas | You want to read the generated script in the graph. |
| ComfyUI-sol-attn | sol-attn | Memory-efficient attention, chunked feed-forward | Only if you enable those two VRAM/SPEED switches. |
| comfyui-minimax-h3-blockcache-T8 | T8 | Block cache | Only if you enable that VRAM/SPEED switch. |
| [ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) | city96 | GGUF checkpoints and encoders | Only if you run quantised models. |

**GGUF users:** install ComfyUI-GGUF, then run the arch patch once:

```bash
cd ComfyUI/custom_nodes/ComfyUI-H3-Multishot
python apply_gguf_arch_patch.py
```

This teaches ComfyUI-GGUF the `minimax_h3` architecture. See [Troubleshooting](#troubleshooting) if you still get an architecture error.

---

## Models

**Diffusion checkpoint (required).** MiniMax-H3. The workflows ship on **`ref2va`**; **`fl2va`** chains equally well and is lighter — see [Which checkpoint](#which-checkpoint). Either way it is the checkpoint's *trained continuation task* that makes the joins work.

### Which checkpoint

Both H3 variants chain, and they differ in what else they can carry.

- **`ref2va` — the shipped default.** Carries *reference rows*, which is the
  mechanism behind voice anchoring (`voice_ref`, `self_anchor_voice`) and the
  identity bank. Reference tokens ride through every sampling step, so it is
  somewhat slower and wants a little more headroom.
- **`fl2va`.** The first/last-frame variant. Lighter and faster, no reference
  rows — so voice anchoring and the bank do nothing on it, and turning them on
  only costs tokens. It chains just as well; the voice rides the frame relay
  and the join's audio reference instead of being explicitly pinned.

**Blind review passed on the `fl2va` configuration.** `ref2va` ships as the
default because it makes voice and character identity explicit rather than
emergent. To take the reviewed path: set the checkpoint to `fl2va` and turn
`self_anchor_voice` off.



GGUF quants: <https://huggingface.co/joeygambino/MiniMax-H3-GGUF>

| Quant | Card size it targets |
| --- | --- |
| `Q8_0` | 32GB |
| `Q5_1` | 24-32GB |
| `Q4_0` | 16GB |

The `curve` variants on that repo are pruned-form requants of the same weights.

**Text encoder and VAEs (required).** <https://huggingface.co/Comfy-Org/MiniMax-H3>

If you use a **GGUF text encoder** it needs its `-mmproj-*.gguf` vision sidecar — that path is what carries frames between shots. Load it with this pack's **H3 CLIP Loader (safetensors + GGUF)**, not the stock `CLIPLoaderGGUF`. Encoder quants: <https://huggingface.co/joeygambino/MiniMax-H3-encoder-GGUF>

ComfyUI-GGUF pairs the sidecar by **filename**, scanning only the encoder's own folder for a `.gguf` containing both `mmproj` and the encoder's stem. Rename either file, or split them across folders, and the match fails — upstream then logs an error and continues *without* the vision tower, which presents as the model ignoring your reference image. This pack's loader never does that:

- it **raises** rather than continuing blind;
- if the name match fails but exactly one mmproj sits beside the encoder, it uses that one and says so;
- and the `mmproj_name` widget lets you point straight at any sidecar, after which **names and folders stop mattering**.

**ref2va (optional).** Only needed for the reference/bank workflows. Seamless chaining does not use it.

---

## How the chaining works

H3 renders a block. Two blocks placed end to end normally read as a cut: the second block re-imagines the scene from text, so faces, wardrobe, framing and colour all shift at the boundary. Both mechanisms below attack that by carrying real rendered state across the join instead of re-describing it.

### 1. `first_frame` - the frame relay

Classic `H3MultishotSampler`. No third-party dependency.

Each shot's **last frame** is handed to the next shot as its **first frame**, through fl2va's *trained continuation task* - the same conditioning path the checkpoint was trained on for image-to-video, not a bolted-on hack. Because the next shot is generated *from* that picture rather than from a fresh reading of the prompt, the pixels at the boundary are continuous by construction: same face, same wardrobe, same lighting, same colour balance.

Two cleanups make the join invisible:

- The **duplicated boundary frame** is trimmed. Shot N's last frame and shot N+1's first frame are the same picture; leaving both in produces a one-frame stutter.
- The **seam audio** gets a **40ms equal-power weld**. Equal-power (rather than linear) crossfade keeps perceived loudness constant through the overlap, so the join does not dip.

### 2. `context_pin` - the raw-latent pin

`H3MultishotMemorySampler` with `continuity=context_pin`. Requires ComfyUI-H3-Motion-Context.

Instead of one frame, the previous shot's **last 22 frames** ride into the next shot **as raw latents** - bit-identical, with no VAE round trip - placed at *interior keyframe coordinates*, alongside a timeline-placed audio reference.

Why this is stronger than the frame relay:

- **No VAE round trip.** A decoded-and-re-encoded frame is not the frame the model produced; the codec loss at exactly the boundary is where colour and micro-texture drift enters. Passing latents keeps the handoff bit-identical.
- **22 frames of motion, not one still.** A single frame tells the model where things *are*. Twenty-two frames tell it where things are *going* - velocity, gesture direction, head turn, camera drift - so motion carries through the join instead of restarting from rest.
- **Interior coordinates.** The pinned latents sit inside the new shot's timeline rather than only at frame 0, so the model regenerates *through* the shared window and matches it, rather than departing from it.

The regenerated **0.92s head** (22 frames at 24fps) overlaps material you already have, so it is trimmed on decode. This is why the first second of every chained shot is discarded replay - see the boundary rules.

### Which one to use

`context_pin` is the shipped default and the tighter join. `first_frame` is the zero-dependency path and is verified across multi-shot chains in its own right. Both are real seamless mechanisms; the choice is dependency tolerance versus join tightness.

---

## Identity without reference images

Most chaining approaches hold a character by feeding reference images into every shot. This pack does not need them, and that is the point: **a 40-second two-character scene was rendered with zero reference images supplied**, and both characters held.

Two stacked mechanisms do it:

1. **The frame relay pins the instance.** Every shot after the first begins from an *actual rendered picture* of the character. The face and wardrobe propagate as pixels, not as a text description the model re-interprets. There is nothing to re-imagine, because the starting state is already correct.
2. **Byte-identical text pins the category.** The prompt writer repeats each character's appearance block **verbatim** in every shot - same words, same order, no paraphrase. Sampling noise around a slightly reworded description is exactly how a face drifts between shots; identical tokens remove that degree of freedom.

Frame pins the instance, text pins the category. Neither is sufficient alone: the relay without stable text lets the model gradually re-interpret the person over many hops, and stable text without the relay just gives you a well-described stranger every shot.

This is also why `seed_per_shot` should stay ON - see the settings table.

---

## Settings reference

### MASTER CONTROLS (`H3StudioControls`)

| Setting | Shipped | Notes |
| --- | --- | --- |
| Resolution | `1280x736` | Drives the sampler and is reported to the prompt writer. |
| Frames per shot | `362` | ~10.1s at 24fps. Sits on H3's frame grid. Also sets the writer's dialogue budget. |
| Steps | `14` | Part of the verified recipe. |

### Sampler dials

| Dial | Shipped | What it does |
| --- | --- | --- |
| `shot_count` | `0` | `0` = one shot per prompt block in the script. A number forces that many shots. |
| `seed_per_shot` | `ON` | Derives a distinct seed per shot. **Leave this ON.** Measured: per-shot seeds *hold* the face; reusing one seed for every shot drifted both face and voice. |
| `continuity` | `context_pin` | `first_frame` (no deps), `context_pin` (needs Motion-Context), `flf_chain` (hard boundary-plate mode; requires plates, and raises an error without them). `seamless`/`seamless_tail` are legacy comparison modes: `seamless` is a soft latent-only pin that often reads as a cut; `seamless_tail` conflicts with Motion-Context and stops up front when that pack is installed. |
| `chain_gain_control` | - | Set to `flatten` on chains past about 5 shots. Seam texture ratchets roughly 1.3x per join - each shot sharpens the one after it - and `flatten` stops the compounding. |
| `color_level` | `off` | `off` / `mvgd` / `scene`. Levels each shot's colour and exposure statistics to shot 1's *settled tail* - a fixed reference, because matching each shot to its neighbour re-accumulates drift. Not needed when chaining by latents; reach for it if a long chain drifts warm or cool. |
| `self_anchor_voice` | - | Feeds shot 1's own rendered audio forward as the voice reference for later shots, so the voice identity established in shot 1 is what later shots match. |
| `voice_ref` | - | An external audio clip used as the voice reference instead. |
| `two_pass_upscale` | `OFF` | Enables the two-pass upscale path. **Not combinable with `continuity = context_pin` or `latent_handoff`, or with an audio spine** - those carry the previous shot's raw latents, or one locked denoise trajectory, across the join and a two-pass render preserves neither; the node errors instead of weakening the join. Available on `cut`, `seamless`, `seamless_tail`, `first_frame`, `flf_chain`. |
| `upscale_factor` | - | Upscale multiplier for pass 2. |
| `pass1_fraction` | `0.4` | Fraction of the step schedule spent in pass 1. **0.4 is the verified value.** Past roughly 0.5 a ghost/moire lattice appears in the output. |
| `upscale_audio_denoise` | - | Denoise applied on the audio lane during the upscale pass. |
| `reference_image_size` | - | `match` (use the render resolution) or `max`. |
| `preview_first_shot` | `ON` | Surfaces shot 1 as soon as it finishes so you can check framing and voice before the rest of the chain renders. |

### VRAM/SPEED switches (`H3StudioSwitches`)

| Switch | Shipped | Requires |
| --- | --- | --- |
| Memory-efficient attention | `OFF` | ComfyUI-sol-attn |
| Chunked feed-forward | `OFF` | ComfyUI-sol-attn |
| Block cache | `OFF` | comfyui-minimax-h3-blockcache-T8 |

All three OFF reproduces the verified recipe exactly. The gates are lazy — an OFF patch never *executes* — but the patch nodes must still *exist* for the graph to validate, so the packs are required (or delete the three patch nodes and their gates). There is also an activation-reserve control here for overriding ComfyUI's inference-memory estimate.

### Shipped workflow defaults

```
1280x736  |  362 frames/shot  |  14 steps  |  euler + beta57 (full; RES4LYF) / beta (CORE, stock)
continuity = context_pin      |  ref2va checkpoint   |  bank ON
all VRAM switches OFF         |  preview_first_shot ON
24fps mux -> output/video/H3CHAIN/  (+ paired audio file)
```

---

## Prompting and boundary rules

These are render-verified. The FULL workflow's prompt writer applies them automatically via `join_style`; **hand-written scripts must follow them manually.** Ignoring them is the most common cause of a chain that looks seamless but sounds wrong.

- **AIRLOCK.** Every shot after the first **opens holding the previous shot's exact closing arrangement**, with about two quiet seconds before anyone speaks. Quiet means real micro-motion - a breath, a weight shift - not a freeze.
- **The first ~1 second of every chained shot is discarded replay.** Dialogue placed at frame 0 loses its opening syllables. This is not a bug to work around; it is the overlap window that makes the join seamless.
- **LAND SETTLED.** End each shot back in a stable arrangement, dialogue finished, with about two seconds spare.
- **A spoken line never straddles two shots.** Budget: *dialogue + 4 seconds of quiet must fit the shot length.* At 243 frames one long line fits. At 124 frames it does not.
- **Repeat verbatim.** Each character's appearance description **and** the room/lighting description are repeated word-for-word in every shot. See [Identity without reference images](#identity-without-reference-images).
- **Keep fps at 24.** Other frame rates audibly shift voice accents.

Script format: one prompt per shot, `---` between shots. JSON (`{"prompts": [...]}`) is also accepted.

---

## Files in the release zip

```
MiniMax-H3_Seamless_Chain_v2.0.zip
  ComfyUI-H3-Multishot/__init__.py
  ComfyUI-H3-Multishot/h3_multishot_utils.py    (samplers, loaders, gates)
  ComfyUI-H3-Multishot/h3_episode_tools.py      (StudioControls, StudioSwitches, AnySwitch)
  ComfyUI-H3-Multishot/h3_lora_stack.py         (H3LoraStack)
  ComfyUI-H3-Multishot/h3_gguf_arch.py          (teaches ComfyUI-GGUF the minimax_h3 arch)
  ComfyUI-H3-Multishot/apply_gguf_arch_patch.py
  ComfyUI-H3-Multishot/LICENSE
  workflows/H3_Seamless_Chain_v2.json           (full)
  workflows/H3_Seamless_Chain_CORE.json         (zero third-party deps)
  INSTALL.md  SETTINGS.md  PROMPTING.md
```

---

## Troubleshooting

### A word is clipped at a join

Two causes, in order of likelihood.

1. **The script put dialogue at the head of a shot.** The first ~1s of every chained shot is discarded replay, so an opening syllable there is trimmed away with it. Fix it in the script: apply the AIRLOCK rule and give the shot about two quiet seconds before anyone speaks.
2. **The seam cut landed on speech.** v2.0's smart weld searches the incoming shot's first 0.75s for the quietest gap and cuts there instead of at sample 0. If you are on an older release, or the shot head has no quiet gap at all to find, the weld has nothing to work with - the fix is still the script.

Also check that no single spoken line straddles two shots, and that `dialogue + 4s` fits your `frames_per_shot`.

### Each shot is sharper than the last

This is the seam sharpening ratchet: texture compounds roughly **1.3x per join**, so it is invisible at 3 shots and obvious at 8. Set:

```
chain_gain_control = flatten
```

Recommended on any chain past about 5 shots.

### The render stalls at 0 steps, or runs ~5x slower than it should

Almost always a **VRAM spill into system RAM**: the DiT loads only partially and streams the remainder from RAM on every step. v2.0 detects this and names it in the ComfyUI console - check there first, because it used to present as an unexplained slowdown with no message.

Remedies, in order:

1. Lower resolution or `frames_per_shot`, or use a smaller quant (`Q5_1` for 24-32GB, `Q4_0` for 16GB).
2. Set the activation-reserve override on the VRAM/SPEED panel. ComfyUI's inference-memory estimate is very conservative at large frame counts, and reserving a measured value instead reclaims the difference for resident weights.
3. Enable the VRAM/SPEED switches (their packs are part of the full workflow's requirements). These change the numerics slightly, so they are OFF by default - turn them on only after you have a baseline you trust.

### Red or missing nodes when the workflow loads

You loaded `H3_Seamless_Chain_v2.json` (the FULL graph) without one of its required packs. Either:

- install the missing pack from the [Optional](#optional) table - the node's title tells you which one - or
- load `H3_Seamless_Chain_CORE.json` instead, which has no third-party nodes at all.

If **every** node from this pack is red, the pack itself did not load: confirm it is in `ComfyUI/custom_nodes/`, confirm ComfyUI is **v0.30.0+**, and read the console for an import error on startup.

### `Unexpected architecture type in GGUF file: 'minimax_h3'`

ComfyUI-GGUF validates a GGUF's architecture against a fixed list and rejects the file before reading any tensors; upstream's list has no `minimax_h3` entry. The quant is fine. This pack teaches it that architecture. If you see the error anyway, the patch is not active - apply it on disk and restart:

```bash
cd ComfyUI/custom_nodes/ComfyUI-H3-Multishot
python apply_gguf_arch_patch.py
```

If a **GGUF text encoder** fails with a state_dict or vision mismatch instead, you are loading it with the stock `CLIPLoaderGGUF`. Use this pack's **H3 CLIP Loader (safetensors + GGUF)**. If it reports no vision sidecar resolved, set its `mmproj_name` widget to the sidecar directly — that bypasses filename pairing entirely.

### Audio gets duller the longer the chain runs

Real and expected: each hop costs a little audio brightness, and it accumulates. There is no dial for it. The working practice is to **restart the chain on scene cuts** - render a long scene as several chains and cut between them, rather than as one chain of many hops. Very long chains are explicitly in the not-yet-verified list below.

---

## Verified / not yet verified

Stated honestly, because the difference matters when you are budgeting GPU hours.

**Verified**

- A 3-shot `context_pin` chain and multi-shot `first_frame` chains were reviewed **blind** by two independent video-understanding models. One described the result as one continuous unedited take, colour consistent, with nothing broken.
- Verified on **both** static talking-head content and dynamic moving content.
- Identity held across a **40-second two-character scene with zero reference images** supplied.
- The blind-reviewed recipe: **fl2va checkpoint, euler sampler, beta57 scheduler, 14 steps, 362 frames per shot (~15.1s at 24fps)**, all VRAM/SPEED switches OFF, no voice anchor.
- The **shipped** defaults differ deliberately: `ref2va` with `self_anchor_voice` and the bank on, for explicit voice and character identity. That combination has **not** been through blind review — it is the same chaining mechanism with reference rows added.
- `pass1_fraction = 0.4` for the two-pass upscale.
- `seed_per_shot` ON holds the face; one seed shared across shots drifted face and voice.

**Not yet verified**

- **Very long chains.** Audio dulls slightly per hop. Restart chains on scene cuts.
- **The ref2va + bank + `context_pin` combination.** Untested together.
- **Hard-FFLF boundary-plate mode** (`flf_chain`). It now fails loudly without plates rather than rendering an unanchored chain, but the mode itself has not been validated.

If you get a result outside this envelope, good or bad, an issue with the settings block is genuinely useful.

---

## Credits

- **MiniMax** - the H3 model.
- **Comfy-Org / ComfyUI** - native H3 support and the text encoder + VAE distribution.
- **NikoDemon80** - [ComfyUI-H3-Motion-Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context), the raw-latent motion-context mechanism `context_pin` is built on.
- **city96** - [ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF).
- **pythongosssss** - [ComfyUI-Custom-Scripts](https://github.com/pythongosssss/ComfyUI-Custom-Scripts) (`ShowText` preview).
- **JoyAI Echo** - ComfyUI_JoyAI_Echo_GGUF_Nodes, the `JoyEcho_LLMEnhance` prompt writer.
- **ComfyUI-sol-attn** - memory-efficient attention and chunked feed-forward.
- **comfyui-minimax-h3-blockcache-T8** - block cache.
- **@viralesveras** - keyframe position parsing and `images_batch`, contributed upstream in this repo.

Pack and workflows by **jlucasmcrell** (GitHub) / **joeygambino** (Hugging Face, Civitai).

## Support

Everything here is free and stays free. If it saved you a night of debugging:

- [Ko-fi](https://ko-fi.com/joeygambino)
- [GitHub Sponsors](https://github.com/sponsors/jlucasmcrell)
- [Liberapay](https://liberapay.com/joeygambino) (recurring)

## License

See `ComfyUI-H3-Multishot/LICENSE` in the release.
