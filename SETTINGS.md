# Settings reference

Everything below documents what a dial does, what the shipped default is,
and what breaks if you move it.

The shipped values are a working production configuration, not a
theoretical best. Three of them are deliberately non-default:
`audio_lock` off, `join_anchor_noise` 0.002 and `join_blend` on.

Shipped defaults favour explicit identity: `ref2va` with voice self-anchoring
and the bank on. The configuration that went through blind review was the
lighter one - `fl2va`, no reference rows - and switching to it is two
changes (see *Checkpoint choice*). Both chain seamlessly.

---

## The shipped recipe

```
checkpoint   MiniMax-H3 ref2va (GGUF Q8_0 / Q5_1 / Q4_0)
sampler      euler
scheduler    beta57     (full workflow; needs RES4LYF)
             beta       (CORE; stock ComfyUI)
steps        14
frames/shot  362        (~15.1 s at 24 fps, the trained maximum)
resolution   1280 x 736 (landscape) or 768 x 1344 (vertical)
fps          24
```

**On the scheduler.** `beta57` comes from RES4LYF, not stock ComfyUI. Measured
on an identical seed, it scored 10/10 for lip-sync against 8/10 for stock
`beta` ("slight synthetic stiff quality to the mouth"), with image quality,
skin texture, artifacts and audio judged equal. The full workflow ships
`beta57` and lists RES4LYF as required; CORE ships `beta` so it keeps its
zero-third-party-pack promise. Switching is one widget either way.

Both orientations sit under the model's pixel ceiling. Resolution **cannot
change mid-chain** — every shot in one run must be the same size.

---

### Checkpoint choice

`ref2va` (shipped) carries **reference rows** - the mechanism behind
`voice_ref`, `self_anchor_voice` and the identity bank. Those three do
nothing on `fl2va`, which has no reference rows; on `fl2va` they only cost
tokens on every sampling step. `fl2va` still chains well - the voice is
carried by the frame relay rather than pinned - and it is the configuration
that went through blind review.

Rule of thumb: **ref2va** when you want voice or identity explicitly
anchored, **fl2va** when you want the lightest, fastest chain.

## MASTER CONTROLS (`H3StudioControls`)

One panel drives `width`, `height`, `frames_per_shot` and `steps` on the
sampler, and — in the full workflow — the prompt writer's dialogue pacing,
so the LLM sizes lines to the real shot length.

The panel also emits `sampler_name` and `scheduler` as strings. Those cannot
link to the sampler's combo widgets on current ComfyUI frontends, so they go
to the sampler's `sampler_override` / `scheduler_override` inputs instead:
when connected they win, and when nothing is connected the sampler's own
widgets apply.

`shot_count` on the panel drives the sampler *and* the prompt writer's
`num_shots`, so the two can never disagree. `0` means one shot per prompt in
the script, and lets the writer decide how many to write.

`use_file_prompts` selects where the scene comes from: **off** reads the
manual scene-idea box, **on** reads the prompt set (file or folder). The
switch is lazy, so the branch you are not using never executes.

---

## Sampler dials

### Chaining

| Dial | Default | What it does |
|---|---|---|
| `shot_count` | `0` | `0` = one shot per script prompt. `1..8` forces the count. |
| `continuity` | `context_pin` (full) / n/a (CORE) | `context_pin` pins the previous shot's last 22 frames as **raw latents** — needs the Motion Context pack. `first_frame` uses the model's own trained hand-off — no extra pack. `cut` for episodic work. `seamless` and `seamless_tail` are **legacy** modes kept for comparison: `seamless` is a latent-only soft pin and often still reads as a cut; `seamless_tail` needs interior keyframe anchors and **conflicts with the Motion-Context pack** - with it installed the run stops up front with the alternatives named. |
| `chain_gain_control` | `off` | Set to `flatten` for chains past about 5 shots. Each shot's tail anchors the next and the model returns ~1.3× the anchor's texture energy, so sharpness **ratchets** across a long chain with a visible step at every seam. `flatten` levels every shot to one house texture. |
| `color_level` | `off` | Levels each shot's colour statistics to shot 1's settled tail. Not needed when chaining by latents — colour already carries. Useful if you see a warm/cool drift across a long chain. |

### Identity and voice

| Dial | Default | What it does |
|---|---|---|
| `seed_per_shot` | `ON` | **Leave it on.** Measured: varying the seed per shot *holds* the face; using one seed for every shot drifted both face and voice. Identity lives in the conditioning, not the seed. |
| `start_image` | unwired | An identity anchor image. Seeds shot 1 and anchors appearance. Optional — the frame relay plus verbatim descriptions usually suffice. |
| `reference_images` | **gate off** | A batch of character portraits carried into **every** shot as `<Picture 1>`, `<Picture 2>`… Bind them in the prompt text. Needs a ref2va checkpoint. Fed by the **REFERENCE** lane in the anchors column: two `LoadImage` nodes → `ImageBatch` → **REFERENCE gate**. Flip the gate on and point the loaders at your portraits; chain another `ImageBatch` for a third and fourth. Unlike `start_image` these are not a first frame — they do not constrain shot 1's composition, they only carry who the person is, and they are what covers shot 1 while the memory bank is still empty. |
| `voice_ref` | unwired | A clean solo speech clip, carried into every shot as `<Audio 1>`, pinning the voice. |
| `self_anchor_voice` | **`on`** (needs `ref2va`) | Shot 1's *own rendered voice* becomes the reference for every later shot — no file needed. Write shot 1 with a clean solo line. Needs a ref2va checkpoint; a wired `voice_ref` takes priority. Note it enlarges the activation pool on every shot after the first. |

### Two-pass upscale

| Dial | Default | What it does |
|---|---|---|
| `two_pass_upscale` | `off` | Renders each shot low-res through part of the steps, upscales in latent space, finishes at full resolution. Faster than native full-res, sharper than low-res alone. Needs the H3 latent-upscaler pack. **Not combinable with `continuity = context_pin` or `latent_handoff`, or with an audio spine** — see below. |
| `upscale_factor` | `1.5` | Pass 1 renders at size ÷ factor, snapped to /32. Pass 2 always lands exactly on the target size. |
| `pass1_fraction` | `0.4` | Share of steps spent low-res. **0.4 is verified clean.** Past roughly 0.5, pass 2 starts at too low a sigma to erase the latent-upscale interpolation pattern and the output grows a ghost/moiré lattice. |
| `upscale_audio_denoise` | `0.35` | How much pass 2 may rewrite the audio. `0` locks pass-1 audio (safest for voice identity), `1` is a full remix. |

**Why two-pass and the strongest joins exclude each other.** `context_pin` and
`latent_handoff` carry the previous shot's *raw latents* into this shot's grid.
Pass 1 runs on a smaller grid, so those latents do not fit — and resampling
them would destroy the bit-identical hand-off that is the entire reason the
mode exists. An audio spine is excluded for a different reason: the spine holds
audio still through every step of *one* denoise trajectory, and a two-pass
render is two trajectories, so half the audio would sample unlocked. In all
three cases the node stops with an error naming the conflict rather than
quietly producing a weaker join. Two-pass is available on `cut`, `seamless`,
`seamless_tail`, `first_frame` and `flf_chain`.

### Workflow

| Dial | Default | What it does |
|---|---|---|
| `preview_first_shot` | `off` | Writes shot 1 to `output/video/H3_FIRSTSHOT/` the moment it decodes — minutes before the chain finishes — so a bad take can be cancelled early. The full path is printed to the console. |
| `reference_image_size` | `match` | `max` uses 2048 px references for best identity fidelity, but reference tokens ride through every sampling step, so it can be several times slower. |
| `seed` | randomize | Fix it to make a good take reproducible. |

---

## Prompt writer (`JoyEcho_LLMEnhance`)

| Dial | Default | What it does |
|---|---|---|
| `unload_model_after` | `off` | Frees this writer's model from Ollama the moment the script is written, so the video model gets the card. Uses this node's own `base_url` and `model_name`. **Turn it on whenever the writer is local.** |

A local writer and H3 want the same GPU, and ComfyUI's eviction cannot help —
it frees models inside the ComfyUI process, while Ollama is a separate process
with its own allocator. Ollama's OpenAI-compatible endpoint cannot be asked
either: its request type has no `keep_alive` field and the shim never sets one,
so the parameter is silently dropped and the model sits for the server default
of five minutes — the whole of shot 1. This switch calls Ollama's native
endpoint, which honours it.

The switch is added to the writer **at runtime by this pack**, so that pack is
not modified and the switch is simply absent when it is not installed. It is
off by default. `JoyEcho_LLMEnhance` is RealRebelAI's node, from
ComfyUI_JoyAI_Echo_GGUF_Nodes.

---

## VRAM / SPEED panel (full workflow only)

**Start with every switch off and the reserve at 0, and try a render before
touching anything here.** That is both the verified recipe and, in practice,
the fastest route to a working chain: the activation reserve measures each
shape and conditioning payload as it renders and sizes the pool itself. It has
held on 32 GB and 24 GB cards alike. These switches are for digging out of a
spill the console has already reported, not for pre-emptive tuning.

The gates are lazy — an off patch never executes, so leaving them alone costs
nothing.

- **`sol_attn`** — memory-efficient attention. The biggest VRAM saving at
  high resolution or long shots. Small quality risk; A/B one render before
  trusting it on a keeper.
- **`chunk_ffn`** — chunks the feed-forward pass. Moderate VRAM saving,
  small slowdown, no known quality cost.
- **`block_cache`** — skips near-duplicate transformer blocks. This buys
  **speed, not VRAM**, and can exaggerate high-frequency texture. Keep it
  off for final masters.
- Other toggles on the panel are not wired in these workflows.

**VRAM RESERVE** sets activation headroom on the model loader. **Leave it at
`0`.** A hand-set number *overrides* the measurement, so a value that suited
one shape becomes wrong for the next — and too little headroom makes a
high-resolution render **stall silently at 0 steps** rather than erroring,
because the driver pages to system RAM instead. Set a value only to recover
from a spill the console has named.

The reserve heuristic measures each shape *and conditioning payload*
separately (a bare shot 1 and a reference-laden shot 2 need different
pools), and prints a named diagnosis if a run does spill:

```
[H3AutoReserve] SLOWDOWN: 299s/step vs 59s/step earlier this session (5.1x).
  This is the VRAM-spill signature: the driver is paging to system RAM
  instead of erroring. Fix: raise the activation reserve, drop
  resolution/frames, or remove reference payload.
```

---

## Seam audio

Automatic, no dials. The boundary cut lands in the **quietest gap** within
the incoming shot's first 0.75 s rather than blindly at sample zero, then a
40 ms equal-power weld joins the two shots. A word placed at a shot head
survives.

If you still hear a clipped word at a join, the script put dialogue too
close to a boundary — see `PROMPTING.md`.

---

## Keyframe anchors and Motion Context

The pack can place keyframe anchors at **arbitrary** frame positions, not
just first and last. Two implementations exist for that and they patch the
same place, so exactly one owns it at a time:

- **ComfyUI-H3-Motion-Context installed** → that pack owns it. Its version
  is a superset (per-row coordinates plus audio timeline placement), so this
  pack detects it at import and stands down with a line in the log.
- **Not installed** → this pack's own `h3_interior_patch` fills the gap.

Either way, stock first/last anchors always work and you do not have to
choose. If you see a log line about standing down, that is the healthy path.

---

## Known limits

- Audio dulls slightly per hop on **long** chains. Restart the chain on a
  scene cut, where a fresh start costs nothing.
- Resolution is fixed for the duration of a chain.
- `flf_chain` (hard first/last-frame boundary plates) is implemented but
  needs a colour-matched plate set; without plates wired it now raises a
  clear error rather than silently rendering unanchored.
