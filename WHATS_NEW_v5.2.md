# Studio 5.2 — Second-pass residual jitter removal

## Automatic two-pass workflow

1. Open the original in Video loop studio and click **Precision shaft lock**.
2. Select/inspect the straight-shank band as before, or import `examples/MVI_5090_two_pass_settings.json` for the supplied MVI_5090 clip.
3. Leave **03 / Second pass — Run a second pass on the completed first-pass video** enabled. It defaults on for shaft processing; existing presets without this setting use the new default. A saved explicit off setting is respected.
4. Click **Apply shaft lock to all frames**. Pass one finishes and verifies its rendered file. Pass two then independently decodes that file, measures its remaining shaft movement and renders small corrections. It does not return to the original footage or rerun the original mask/crop.
5. Use **Compare first / second pass** to switch between the two results. The status identifies which one is shown. Choose the second-pass result for final export.
6. Find/review loop points after both passes. Colour grading and the logo are applied during final export as before.

The old per-frame render refinement remains part of pass one. This new pass is a separate analysis and render of the completed first-pass file.

## Controls

- **Strength %:** 100 applies the complete residual-jitter correction up to the limits; lower values retain more original movement.
- **Smooth seconds:** Gaussian trajectory smoothing, default 0.12 seconds. Increase it for slower residual swaying; smaller values mainly address rapid jitter. This is the Gaussian time scale, not the duration of a frame window.
- **Max shift px:** default 3 output pixels at the measured shaft anchor, separate from pass one's percentage limit.
- **Max angle:** default 0.5 degrees, separate from pass one's maximum aim angle.
- **Run a second pass:** disable this to render and retain only pass one. All controls are saved with shaft presets and app defaults.

The second pass reduces frame-to-frame shaft-axis jitter while preserving slower trajectory changes, deliberate spin, size, resolution, FPS and frame count. It corrects sideways shaft movement and small tilt; a straight-shank band cannot measure movement along the shaft's own length. It does not reconstruct bending, depth movement or motion blur.

## Run later on a first-pass result

If you disabled automatic pass two, complete pass one, then click **Second pass on processed video…** in the video toolbar. Set its controls and run it. This processes the existing rendered first-pass result without repeating pass one. The current session must contain that first-pass result; reopening an arbitrary MP4 does not restore the processing state.

An already completed second pass cannot be accidentally stacked again. To change the settings, edit them in Precision shaft lock and apply a fresh two-pass process. Comparison switches invalidate the loop candidates because each pass has different pixel content. The final export uses whichever pass is currently selected.

## Transparency, output and safety

Transparent first-pass ProRes MOV output keeps its alpha during the second pass; hidden RGB colours and checkerboard previews are not used for tracking. RGB and alpha are resampled together with premultiplied edge handling. Background removal, safety crop and replacement colour are not applied twice. The measurement band is adjusted for the first pass's safety crop.

Opaque footage gets one additional high-quality H.264 working encode; transparent footage uses ProRes 4444. Additional resampling/encoding can slightly soften fine detail, so compare both passes before final export. The first-pass file is retained until the result is closed. Sources are preserved, and a failed automatic second pass leaves any previous working result unchanged. Disable pass two to obtain a fresh first-pass-only result if its tracking fails.

Both passes require a reliable straight-shank band. Pass two rejects tracking below 90% or long gaps. Short gaps and safety-limit events are reported. The exported `.loop.json` records both passes, including the second-pass settings, tracking count, limits and a checksum identifying the first-pass file it actually analysed. Colour presets remain separate `.colour.json` files.

## Checked on MVI_5090

All 436 frames were retained and tracked in both passes with no missing frames or safety-limit events. Remeasuring the encoded output with the same tracker showed small further reductions in high-frequency residual jitter: sideways RMS 0.02890 -> 0.02475 px and tilt RMS 0.02866 -> 0.02419 degrees. These are tracker estimates, not a claim of perfect physical steadiness. Overall drift/extreme ranges need not decrease because this pass targets rapid jitter rather than locking all slower motion.

The full measurements and settings are in `examples/MVI_5090_two_pass_report.json` and `MVI_5090_two_pass_settings.json`. The existing MP4 examples in this package are the earlier v5.1 single-pass examples, not newly rendered two-pass demonstrations.
