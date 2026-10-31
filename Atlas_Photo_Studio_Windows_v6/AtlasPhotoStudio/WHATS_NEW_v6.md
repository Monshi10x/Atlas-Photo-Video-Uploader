# Studio 6.0 — Advanced verticality and wobble compensation

## What changed

The Precision shaft lock dialog now includes an **Advanced strategy** tab with three new methods in addition to the existing tracker:

| Strategy | What it measures | When to use it |
| --- | --- | --- |
| Legacy shaft edges | The original subpixel threshold/centre-line fit | Reproduce v5 output or process quickly |
| Robust multi-band edges | Several nearby edge thresholds, robust row fitting, width outlier rejection and agreement across three sections of the band | Plain shanks with small reflections or isolated edge noise |
| Reference geometry mask | A captured mask of the selected shank, rigidly made vertical, then matched independently against each frame | A stable silhouette with sufficient background contrast |
| Hybrid edges + reference mask | Combines edge and mask estimates; falls back to robust edges if mask registration fails confidence checks | A practical starting point when mask confidence varies |

The reference method uses shape geometry, not metal surface texture. Each frame is compared to one fixed reference, so its position is not obtained by accumulating frame-to-frame transforms. Registration uses rigid rotation/translation only; it does not stretch or shear the tool. Unobservable translation along a straight shank is discarded.

**Subpixel** and **cubic** resampling retain continuous subpixel coordinates for tiny corrections. Subpixel uses precise linear interpolation; cubic is sharper and substantially slower. Fast keeps the original interpolation. Working MP4 encodes in either precision mode use high-quality 4:4:4 colour before the normal final video export. Transparent video is resampled with premultiplied RGB/alpha to avoid coloured edge halos.

The second pass now offers **lock** in addition to **smooth**. Smooth removes rapid deviations from a smoothed trajectory. Lock instead targets a zero-degree vertical axis and a fixed median position in the already-rendered first pass, bounded by its own pixel and angle limits. Smooth seconds is disabled in lock mode because it is not used there.

## Use the new controls

1. Extract the package, start the app, open the original video and select **Precision shaft lock**.
2. Keep the measurement band on a long straight portion of the shank, with background on both sides throughout the rotation. Avoid cutting flutes, the base, shadows and logos.
3. Open **02 / Advanced strategy** and choose a method. **Use advanced recommended** selects Hybrid, subpixel resampling and a fixed vertical second pass with a 1 px / 0.5 degree safety limit. These are starting settings, not a guarantee that every clip will benefit equally. Choose cubic if you prefer its sharper rendering and can allow substantially more processing time.
4. Inspect a useful source frame, then choose **Capture shown frame / preview masks**. The popup shows the source shank, captured geometry and its vertical ideal. You can save the ideal mask as a PNG. Alternatively type a reference frame index. A nonzero reference frame is supported.
5. The default minimum mask score is 0.98. Higher values make registration stricter. Hybrid can fall back to robust edges; Reference-only rejects unreliable matches. The status and export report record these events. Do not lower the score to rescue an unsuitable measurement area.
6. Review **03 / Second pass**. Use **lock** to pin residual axis/position; **smooth** remains available for the previous behaviour. Both act on the completed first-pass file, preserving frame count and alpha.
7. Apply, compare the first and second passes, then find loop points and export. Apply the logo and colour grade afterwards as before.

For the supplied clip, `examples/MVI_5090_v6_settings.json` contains a ready-to-import recipe and `MVI_5090_v6_benchmark.json` records the strategy comparison. The earlier v5.1 example MP4 files remain in the package for reference; their filenames have not been relabelled as v6 output.

That clip-specific preset uses **Hybrid + cubic + lock**, selected for its measured angular result. On this clip it reduced angular micro-jitter RMS from approximately 0.02419 to 0.01834 degrees using the legacy evaluator, about 24%. A second image evaluator also showed reduced jitter. The visual improvement is small because the prior result was already quite steady. These measurements are image estimates, not independent physical ground truth. The general recommended button uses the faster subpixel option; cubic processing may take several minutes for a short HD clip depending on the computer.

`examples/MVI_5090_v5_2_vs_v6.mp4` shows the prior two-pass result beside the new clip-specific preset, at original speed, with matching 4x details. The captured shank reference and ideal masks are also included as PNGs.

## Settings and compatibility

Shaft preset export/import and saved app defaults include strategy, reference frame, mask score, resampling and second-pass mode. Old presets remain readable and use the legacy tracker/fast interpolation unless you choose the new controls. New presets require this version. The actual mask is reconstructed from the selected source frame and band; a preset does not contain or substitute another video's pixel data. A saved ideal-mask PNG is a diagnostic, not an importable external template.

Normal photo export, colour recipes, Shopify upload, logo positioning and loop frame conventions are unchanged. Final `.loop.json` includes strategy/correlation settings, reference index, mask acceptance/fallback/rejection counts and both passes. Whole-video tracking quality and final visual inspection still matter.

## Limits

A changing cutting-flute silhouette cannot safely be forced onto one frozen outline. The mask method therefore models the selected stable shank. It does not perform semantic tool recognition, full 3D reconstruction, physical bend correction, depth-tilt correction or motion deblurring. It also cannot infer along-axis height movement from a featureless straight band. All corrections are rigid and preserve the intended spin and tool dimensions.

Very reflective edges, a bad band or insufficient background contrast can still bias all image-based estimates. Inspect the tip as well as the shank and compare strategies. Additional resampling/encoding may soften fine detail. A tightly mounted, concentric tool and a fixed camera remain the strongest starting point.

## Approaches investigated

- **Captured silhouette registration:** implemented on a stable-shank geometry mask. Direct full-tool matching was avoided because rotating flutes legitimately change the silhouette.
- **Multi-band robust geometry:** implemented to limit sensitivity to one threshold, isolated blobs and local transitions.
- **Hybrid confidence gating:** implemented to avoid accepting every template fit and to reduce sensitivity to unreliable edge sections.
- **Feature/optical-flow tracking:** useful for textured objects, but surface features on a spinning polished shank do not provide stationary orientation landmarks. Not used as a default correction source.
- **Cumulative frame-to-frame registration:** not used; a fixed reference avoids integration drift.
- **Temporal averaging of picture pixels:** not used; it can ghost cutting edges. Smoothing/locking affects transform estimates only.
- **Continuous-coordinate linear/cubic rendering:** implemented, including alpha handling. This addresses precision lost when very small geometric corrections are rasterised.

Primary technical references:

- OpenCV geometric registration and optical flow: https://docs.opencv.org/4.13.0/dc/d6b/group__video__track.html
- SciPy continuous-coordinate spline resampling: https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.affine_transform.html
