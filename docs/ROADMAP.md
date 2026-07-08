# Roadmap

This document lists planned features and improvements. It is not a commitment — priorities may shift based on user feedback and development bandwidth.

## Near Term

- **MIDI CC automation export** — volume, filter cutoff, and other modulation lanes as MIDI controllers
- **`--export-format` flag** — subset selection (MIDI-only, JSON-only, etc.)
- **Per-layer swing override** — e.g., hats swing 0.1, kick stays straight
- **`--grid-start-beats`** — grid start as a beat fraction instead of seconds for loop alignment
- **Style renaming** — merge `minimal`/`sparse` overlap, clean up ambiguous style names
- **`--drum-map`** — specify custom MIDI note mapping per instrument
- **`--bars` auto-constrain** — warn if source length is significantly longer than bars

## Medium Term

- **`--style <CUSTOM>`** — user-defined style presets via JSON or inline overrides
- **`--fill-density`** — separate control for fill intensity (independent of master density)
- **`--randomize`** — randomize all controls within bounds for exploration
- **Tempo automation** — gradual BPM changes over the pattern
- **Arrangement refinement** — more structure presets, user-defined arrangement maps
- **Polyrhythm support** — e.g., kick in 4/4, hats in 3/4 over 4 bars
- **`breaksmith merge`** — merge multiple style outputs into a single multi-track MIDI
- **`breaksmith info`** — inspect pattern.json metadata and verify reproducibility

## Long Term

- **Ableton Live Set export** — `.als` file with drum rack, clips, and tempo automation
- **Multi-source input** — separate source for kick grid, hat grid, etc.
- **Stem-aware generation** — use source separation (via demucs or similar) to generate per-stem patterns
- **Harmonic analysis** — key and chord detection for choosing complementary percussion pitches
- **DAW integration** — MIDI clip export that works with Ableton's API or REAPER's ReaScript
- **Real-time preview** — stream generated audio without writing to disk first
- **Onset-guided fill patterns** — fills that match the source's transient profile
- **Style interpolation** — blend between two style presets (e.g., 60% liquid, 40% rolling)

## Non-Goals

The following are explicitly out of scope:

- **Sample replacement** — Breaksmith does not include a sample library or drum kit. The preview synth is for audition only. Import generated MIDI into your DAW and use your own sounds.
- **Full track generation** — Breaksmith generates drum patterns, not complete songs. No melody, bass, harmony, or arrangement of non-percussive elements.
- **Mix/master** — No EQ, compression, reverb, or mastering. Output is dry drum MIDI and a basic synthesized preview.
- **Real-time performance** — No live input, MIDI controller support, or interactive jam mode. Generation is a batch process from audio input to file output.
- **Source modification** — Breaksmith analyzes and uses source features. It does not modify, trim, stretch, or transform the source audio.
- **Cloud/API service** — Breaksmith is a CLI tool. No web API, no SaaS, no database.

## Rejected / Removed

- **"Sparse/balanced/active" variant system** — considered but rejected in favor of continuous density control. A three-mode system was overly prescriptive and less flexible than `--density 0.0–1.0`.
- **Stem/drums-only export** — would require source separation, which is a significant dependency with no clear benefit over sending the whole source through analysis.
- **`--variant` (singular)** — the `--variants` (plural) flag was implemented instead, which generates multiple patterns from different seeds. A singular flag added no value over `--seed`.

## Version History

| Version | Features |
|---|---|
| 0.1.0 | Initial release: analyze, generate (DnB + hip-hop), MIDI/JSON/Strudel export, preview synth, swing/humanize/variation, source restraint, BPM override, click track |
| 0.1.1 | Phrase awareness, groove templates, per-layer density, velocity curves, reproducibility metadata |
| 0.1.2 | Variants, comparison preview, `--preview-bars`, CLI documentation |
| 0.2.0 | Meter support: `--time-signature` and `--beat-grouping` flags, `Meter` dataclass with 4/4, 3/4, 6/8 presets, MIDI time signature meta event, Strudel `setcpm()`, meter-relative click track, 76 new tests |
