# Studio 5.1 — Precision shaft lock

## Why smoothing alone left wobble

Position smoothing follows a moving centre and leaves slow swaying. The old Smart Aim also smoothed the angle before correcting it, leaving fast tilt changes visible. Its whole-silhouette measurement can move as asymmetric cutting flutes rotate. Version 5.1 corrects the current measured Smart Aim angle and adds a separate straight-shaft tracker.

## Reproduce the correction for MVI_5090 - LOOP2.mp4

1. Extract the ZIP and run START.bat. In Video loop studio, open the supplied original video from your computer.
2. Click **Precision shaft lock** in the video toolbar.
3. Click **Import settings** and choose `examples/MVI_5090_shaft_lock.json` from this package. Inspect frame 0 and other frames such as 120 and 360. The gold band covers the straight lower shank; the green line shows the measured axis.
4. The supplied settings use band X=0.46, Y=0.49, Width=0.08, Height=0.36; contrast 18; tracking 1080 px; strength 100%; maximum angle 5 degrees; maximum shift 5%. Original background is retained.
5. Click **Apply shaft lock to all frames**. The status reports tracking success and frames reaching safety limits. A nonzero safety-limit count means correction was bounded and wobble may remain.
6. Find/review loop points on the processed video, then export. Colour Studio and logo overlays apply afterwards as before. The exported loop report includes the shaft settings and tracking statistics; colour recipes remain separate importable colour JSON files.

`examples/MVI_5090_shaft_locked.mp4` is a corrected sample preserving all 436 source frames. `MVI_5090_before_after.mp4` compares original and corrected footage. Both are cropped to the central 400 x 606 px region so the logo already baked into the supplied clip is excluded. No loop retiming or colour changes were applied; exports are silent. The processing report is alongside them.

## Use with another tool

Drag a new band around a long straight part of its cylindrical shank. Leave background on both sides and enough horizontal space for the full sway, and avoid cutting flutes, labels, the base and shadows. Check several frames. The band is a measurement area; it is not the exported image crop.

At 100%, each reliable frame is rigidly rotated onto a vertical axis and shifted to the first reliable frame's axis position. Two small render-feedback corrections reduce edge-resampling residuals. Size and deliberate spin are preserved. Lower strength allows some original motion and disables that final refinement. Smooth seconds is irrelevant to shaft lock.

The precision method decodes up to 1080 px by default rather than measuring the old 256 px navigation proxy. Tracking pixels can be increased to 2160 for fine details. Edge contrast is a local RGB distance from the background at each side of the band: lower it if shaft edges disappear; raise it if noise/background is detected. Higher resolution costs more processing time.

The tracker requires at least 90% reliable frames and rejects tracking gaps longer than approximately 0.15 seconds (with a two-frame minimum allowance). Short gaps are interpolated and reported. Angle/shift safety bounds are retained and reported; do not increase them to compensate for a wrongly selected band. Shaft mode takes precedence over Smooth/Smart Aim. The normal stabilization/background dialog can disable shaft lock or change the background independently. Export/import shaft settings from the shaft dialog; these are distinct from colour presets.

## Limits and capture advice

This locks a measured 2D axis. It cannot reconstruct physical bending, depth tilt/foreshortening, changing visible tip height, blur or an unevenly rotating tool. A uniform straight shank against a plain contrasting background is required. Fluted or strongly patterned bands and reflections can bias the axis. Inspect the cutting end as well as the shank; the app does not claim mathematical perfection of the whole visible product.

For the best source, seat the tool concentrically in a secure collet/chuck, keep the rotating support level and rigid, lock the camera and avoid autofocus or exposure changes during capture. A tool that is physically straight and centred removes motion that software cannot fully recover.

Use original footage before branding, stabilize first, then add the Atlas logo. A logo already burned into source pixels moves with a whole-frame correction. Background removal is optional and has its own colour/mask controls; the example's background is grey-blue, so a white key should not be assumed.

Technical reference for robust line fitting: https://docs.opencv.org/4.5.5/d3/dc0/group__imgproc__shape.html
