"""Rift Script Picker — a dropdown node for selecting a saved prompt JSON.

The stock JoyEcho_TextEncode 'prompts' field only accepts pasted JSON / a typed
path, which is painful in the canvas. This node lists every *.json in
  <ComfyUI>/input/joyecho_prompts/
as a COMBO dropdown and outputs the file's contents, wired straight into
JoyEcho_TextEncode's 'prompts' input (which accepts inline {"prompts":[...]} JSON).

Add a .json to that folder, hit the ComfyUI refresh button (or press R) to
repopulate the dropdown, pick it, run. Editing the file re-triggers execution
automatically (IS_CHANGED tracks mtime) — no need to reselect.
"""

import json
import re
from pathlib import Path

import folder_paths

_PROMPTS_SUBDIR = "joyecho_prompts"
_EMPTY = "(no .json in input/joyecho_prompts)"

# Per-character audio memory needs to know WHO speaks in each shot. That used to
# be a hand-typed speaker_order widget on the Generate node, which does not
# survive a queue-driven workflow - nobody is going to retype it per script. The
# script already states the speaker in every shot, so derive it here and hand it
# downstream. The widget remains as a manual override.
#
# The tags are opaque: save_memory_slot(character=...) and get_memory_audio(
# speaker=...) only ever compare them for equality, so "ID_A" works as well as
# a bare speaker name needs no mapping to a refs folder.
_SPEAKER_RE = re.compile(r"\b(ID_[A-Z]|[A-Z][a-z]+)\s+is\s+talking\b")
LAST_SPEAKERS: list[str] = []

# Voice anchors: {"character": "path/to/clip.mp4"} carried by the script's
# "voice_refs" key. Same stash pattern as LAST_SPEAKERS; the Generate node
# encodes each clip's audio into a tagged memory-bank slot before shot 1, so
# the character's voice is CAST from a file instead of rolled from text.
# Keys must exactly match the script's speaker tags.
LAST_VOICE_REFS: dict = {}


def set_last_voice_refs(refs: dict) -> None:
    """Stash the current script's voice anchors (empty dict clears)."""
    global LAST_VOICE_REFS
    LAST_VOICE_REFS = dict(refs) if isinstance(refs, dict) else {}


def set_last_speakers(speakers: list[str]) -> None:
    """Stash the current script's speaker order for the Generate node.

    Wiring the `speakers` output is the explicit path; this module-level stash is
    the zero-rewiring fallback so existing saved workflows and queued runs pick
    it up with no canvas edits. ComfyUI executes a graph's nodes in dependency
    order within one prompt, so the picker always runs before the generator it
    feeds, and each execution overwrites the previous value.
    """
    global LAST_SPEAKERS
    LAST_SPEAKERS = list(speakers)


def derive_speakers(data: dict, shots: list) -> list[str]:
    """Speaker tag per shot: an explicit "speakers" array wins, else the prose.

    Returns [] when the script declares nothing and no shot names a speaker -
    callers then fall back to character-blind memory, i.e. old behaviour.
    """
    if isinstance(data, dict):
        declared = data.get("speakers") or data.get("speaker_order")
        if isinstance(declared, str):
            declared = [t for t in re.split(r"[,\s]+", declared.strip()) if t]
        if isinstance(declared, list) and declared:
            return [str(declared[i % len(declared)]) for i in range(len(shots))]

    out, seen_any = [], False
    for shot in shots:
        m = _SPEAKER_RE.search(str(shot))
        if m:
            out.append(m.group(1))
            seen_any = True
        else:
            # Unattributed shot: reuse the previous speaker rather than guessing.
            # A wrong tag is worse than a repeated one - it would filter the bank
            # to the wrong character and hand this shot the wrong voice.
            out.append(out[-1] if out else "")
    return out if seen_any and all(out) else []


def _scripts_dir() -> Path:
    d = Path(folder_paths.get_input_directory()) / _PROMPTS_SUBDIR
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def _list_scripts() -> list[str]:
    d = _scripts_dir()
    try:
        files = sorted(p.name for p in d.glob("*.json"))
    except OSError:
        files = []
    return files if files else [_EMPTY]


class RiftScriptPicker:
    """Pick a prompt-script .json from input/joyecho_prompts via a dropdown."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"script": (_list_scripts(),)}}

    RETURN_TYPES = ("STRING", "STRING", "STRING",)
    RETURN_NAMES = ("prompts_json", "path", "speakers",)
    FUNCTION = "load"
    CATEGORY = "H3/script"

    @classmethod
    def IS_CHANGED(cls, script):
        # Re-run when the selected file changes on disk, so edits are picked up.
        p = _scripts_dir() / script
        try:
            return f"{script}:{p.stat().st_mtime}"
        except OSError:
            return script

    def load(self, script):
        if script == _EMPTY:
            raise ValueError(
                f"No .json scripts found. Put your prompt JSON in {_scripts_dir()} "
                "and press the refresh button (or R) to repopulate the dropdown."
            )
        p = _scripts_dir() / script
        if not p.exists():
            raise FileNotFoundError(
                f"Script not found: {p}. Refresh the node list (R) after adding files."
            )
        text = p.read_text(encoding="utf-8")
        # Fail early with a clear message rather than deep in the text encoder.
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"{script} is not valid JSON: {e}")
        arr = data.get("prompts") if isinstance(data, dict) else None
        if arr is None and isinstance(data, dict):
            arr = data.get("shots")
        if not isinstance(arr, list) or not arr:
            raise ValueError(f"{script} must contain a non-empty 'prompts' (or 'shots') array.")
        speakers = derive_speakers(data, arr)
        set_last_speakers(speakers)
        set_last_voice_refs(data.get("voice_refs") or {})
        print(f"[H3 Multishot] ScriptPicker: {script} ({len(arr)} shots)"
              + (f", speakers: {' '.join(speakers)}" if speakers else ", no speaker tags")
              + ".", flush=True)
        return (text, str(p), " ".join(speakers),)


NODE_CLASS_MAPPINGS = {"RiftScriptPicker": RiftScriptPicker}
NODE_DISPLAY_NAME_MAPPINGS = {"RiftScriptPicker": "Script Picker (JSON dropdown)"}

# deprecated alias - saved workflows made before the rename still
# reference the old key; keep it resolving so they open.
NODE_CLASS_MAPPINGS["JoyEcho_ScriptPicker"] = RiftScriptPicker
NODE_DISPLAY_NAME_MAPPINGS["JoyEcho_ScriptPicker"] = "[deprecated] " + NODE_DISPLAY_NAME_MAPPINGS["RiftScriptPicker"]
