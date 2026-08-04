MiniMax-H3 Multishot — v1.1
===========================
(paste this into the Civitai version description)

Chain multiple MiniMax-H3 shots into one continuous video WITH audio — in one node.

WHAT'S NEW IN v1.1
------------------
• IMAGE-TO-VIDEO. The sampler now takes an optional `start_image`. Connect a
  LoadImage and shot 1 begins from your frame, then chains as usual. Leave it
  unconnected and nothing changes — v1.0 graphs keep working.
  (Included: H3_Multishot_AIO_I2V.json — the easy-mode graph with it wired up.)

• ~4x FASTER ON 32GB CARDS. The text encoder is now evicted before sampling.
  The Qwen3-VL encoder (~16.5GB even at Q4) and the H3 DiT (~25GB) do not
  co-fit on a 32GB card, so the DiT was loading PARTIALLY and streaming ~19GB
  from system RAM on every step. If your log ever showed:

      loaded partially; 6423 MB usable, 5847 MB loaded, 19363 MB offloaded

  that was it. Measured on an RTX 5090: ~60 min -> ~15 min for the same render.
  The node now prints "[H3Multishot] TE evicted; NN.N GB free for the DiT".

• TEXT ENCODER GGUF PUBLISHED, including the mmproj vision sidecar that
  multi-shot actually requires (chaining feeds the previous shot's last frame
  through the encoder's vision path — no mmproj, no continuity):
  huggingface.co/joeygambino/MiniMax-H3-encoder-GGUF

WHAT YOU GET
------------
• H3 Multishot Sampler — paste a script (one prompt per shot, `---` between
  them), pick a shot count, get a seam-clean master with continuous audio.
  Each shot starts from the last frame of the previous one; the duplicated
  seam frame and its 1/24s of audio are trimmed automatically.
• Dual-format loaders — same dropdown loads .safetensors or .gguf.
• GGUF quants for 16-32GB cards (Q5_1 / Q4_0, both DiT flavors):
  huggingface.co/joeygambino/MiniMax-H3-GGUF
• Expert workflow with the three shot chains exploded onto the canvas.

FILES IN THIS UPLOAD
--------------------
• H3_Multishot_AIO.json          — easy mode (text-to-video)
• H3_Multishot_AIO_I2V.json      — easy mode + start frame (NEW in 1.1)
• H3_Multishot_3chain_expert.json— per-stage control, fixed 3 shots

REQUIREMENTS
------------
ComfyUI 0.30.0+, the node pack (github.com/jlucasmcrell/ComfyUI-H3-Multishot),
ComfyUI-GGUF + the included one-line arch patch for GGUF models.
Encoder/VAEs: Comfy-Org/MiniMax-H3, or the GGUF encoder repo above.

NUMBERS THAT MATTER
-------------------
• Shots live on H3's 17k+5 frame grid (243 frames ~= 10s; 362 ~= 15s = trained max).
• RENDER AT NATIVE RESOLUTION AND UPSCALE AFTERWARDS. Rendering natively at
  1920x1088 scored WORSE than 960x544 in blind review (softer, reads as an
  upscale) and cost ~4x the time.
• 16GB cards run Q4_0 with automatic streaming.

ROADMAP
-------
ref2va hard mode — identity from reference images and voice clips — plus
deeper multi-frame memory for long-form (2-5 minute) chains.

SUPPORT
-------
Everything here is free and stays free. If it saved you a night of debugging,
tips keep the 5090 warm:
  Ko-fi:      ko-fi.com/joeygambino
  GitHub:     github.com/sponsors/jlucasmcrell
  Liberapay:  liberapay.com/joeygambino
