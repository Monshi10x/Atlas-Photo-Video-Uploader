# Atlas Photo & Video Studio 5.0 — Colour Studio

Extract the ZIP into a new folder and run START.bat. Existing settings/credentials/history are reused. Colour controls are available from **Colour Studio • Photo & Video** above the photo workspace and **Colour Studio** in the video toolbar.

## Editing workflow

1. Select the photo, or open/process the video and select its start frame.
2. Open Colour Studio from that workspace. It displays the source photo or video start frame, before and after your changes.
3. Adjust controls, use the histogram, or use the neutral eyedropper on a neutral grey patch in the BEFORE image.
4. Click **Apply & save defaults**. This saves one shared recipe for the current photo batch and video exports. The main workspace preview updates. This does not modify source files.
5. Export normally. Adjustments are baked into the exported media. The Atlas logo is composited AFTER grading so its colours are preserved.

The source preview in the colour dialog does not include the photo's final crop, white removal, logo or square padding. Inspect the main workspace for that finished composition. Video dialog previews use the selected working clip (original or stabilized/masked), before the final spatial crop/logo. Preview detail and colour are approximate; full exports use their configured output size.

Photo uploads made before a recipe change must be re-exported before upload. The upload guard detects the settings change. Video loop matching continues to use the ungraded working clip, preserving geometric/motion comparisons; grading is applied after stabilization/masking and before the logo in the final export.

## Controls

There are 58 numeric controls and four editable tone curves:

| Section | Controls |
|---|---|
| Light | Exposure in EV, contrast, highlights, shadows, whites, blacks, midtone gamma |
| WB | Relative temperature and tint, vibrance, saturation, RGB channel gains, RGB black/lift balance |
| Detail | Texture, clarity, dehaze, sharpening, luminance noise reduction, colour noise reduction |
| FX | Vignette, vignette midpoint, grain, black-and-white mix |
| Grade | Shadow, midtone and highlight hue/strength, grading balance |
| HSL | Separate hue, saturation and luminance controls for red, orange, yellow, green, aqua, blue, purple and magenta |
| Curves | Master, red, green and blue curves |

Use sliders or type a numeric value, then press Enter or leave the field. The small reset button restores that control's default. **Reset all** resets the full recipe in the dialog; it changes the workspace only when you Apply.

Temperature/tint and black balance are relative display-space adjustments, not a camera-calibrated Kelvin/tint system. Exposure is an approximate linear-light scaling of edited RGB media. Noise/detail/dehaze controls are custom implementations and will not reproduce Adobe's results exactly.

**Neutral eyedropper:** click it, then click a known neutral grey patch in BEFORE. It estimates per-channel gains from that patch and resets relative temperature/tint. Very dark or transparent samples are ignored. The tool cannot infer the true colour of an unknown object: do not neutralize a gold coating or coloured tool surface as though it were grey.

**Curves:** enter normalized JSON control points, such as `[[0,0],[0.25,0.18],[0.75,0.82],[1,1]]`, then preview/apply. Input coordinates must increase strictly from 0 to 1. Output coordinates must be 0–1. Interpolation is piecewise linear. Master is followed by each RGB channel curve.

The histogram shows the after-image's RGB distribution on a logarithmic display. It includes transparent pixels' stored RGB values. Grain uses a deterministic spatial pattern so repeated exports match and video does not flicker from randomized noise. Fine-detail previews may differ from full-resolution exports.

## Presets and automatic settings export

**Export preset** writes an Atlas colour JSON file. **Import preset** reads that file or an automatically exported colour sidecar. Imports are validated for schema version, supported controls, finite numbers/ranges and curve structure. Import loads values into the dialog; Apply commits them.

Every photo export automatically writes a companion file:

- `Atlas Tools ... MAINSHOT CLOSEUP.png`
- `Atlas Tools ... MAINSHOT CLOSEUP.png.colour.json`

Other images similarly receive `.jpg.colour.json` or `.png.colour.json`. The batch manifest records each sidecar path and settings.

Every video export writes:

- `Product - LOOP.mp4` (or transparent `.mov`)
- `Product - LOOP.mp4.colour.json` (or `.mov.colour.json`)
- `Product - LOOP.loop.json`, containing the colour recipe plus the usual frame interval/effects/export information.

Keep the colour sidecar if you want to reproduce the same look. Copy it to another computer and import it through Colour Studio. This recipe contains no API tokens, logo path or machine-specific source path. Full batch/video reports can contain source paths as before.

The sidecar stores the complete adjustment recipe and a version number. It does not contain the source image, crop, logo, stabilization settings or the original unedited pixels. Keep source files and the existing batch/video reports to reproduce the entire workflow. Importing a recipe onto an already graded export applies the look AGAIN: start from the original/appropriate working clip to avoid double grading.

Default recipes are remembered through Save defaults. Bundled example presets are in `presets/`; these are starting points, not tool-specific calibrations. Each media export bakes the selected recipe, regardless of whether you exported a preset manually.

## Video and transparency

Colour export decodes the selected frame interval on the same working FPS grid, applies crop/resize and the recipe to each frame, overlays the logo, re-encodes, then verifies the exact frame count. The duplicate return frame stays excluded. All audio is removed as in earlier versions.

RGB grading preserves alpha unchanged. Transparent processed footage continues to export as ProRes 4444 MOV; opaque footage uses H.264 MP4. Grading affects the full visible image, including any replacement background and square padding. It does not change the chosen segmentation key or mask: masking happens BEFORE grading.

Normal Original/processed toggling compares stabilization/background effects; both versions still show the shared colour recipe in the workspace. Use the colour dialog's BEFORE/AFTER for a grading comparison.

## Scope

This is a Lightroom-style editor for already edited RGB photos and video, not full Lightroom feature parity. It does not implement RAW demosaicing/development, camera/lens profiles, Adobe AI masks, healing/content-aware removal, panorama/HDR merge, catalog management, lens/geometry correction, local adjustment brushes or Lightroom XMP import/export. It cannot recover clipped highlights from a JPEG/video. Atlas JSON presets are importable into this app and are not Adobe-compatible XMP presets.

The existing photo crop, background removal, Smart Aim stabilization, video mask, logo, naming and Shopify upload features remain available. Recipes are shared across the batch; there are no independent per-photo recipes or video keyframes in v5.

## Validation

See VALIDATION.txt. Tests cover neutral identity, alpha preservation, exposure/WB/HSL, every numeric control, preset round-trip, invalid imports, photo sidecars, actual graded video frame counts, logo colours applied after monochrome grading, and transparent MOV grading with alpha-preserving logos. Native UI checks exercise the dialog, preview, eyedropper, import/export recipe round-trip, applying defaults and automatic image sidecars. Windows-native rendering/EXE building and real tool-footage review remain local checks.
