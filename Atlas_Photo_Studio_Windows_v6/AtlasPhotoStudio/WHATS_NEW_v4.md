# Atlas Photo & Video Studio 4.0

Extract into a new folder and run START.bat. Setup installs OpenCV and the FFmpeg runtime automatically; no separate FFmpeg installation is needed. Existing photo defaults, credentials and upload history are retained. This is runnable Python source with a Windows launcher; the optional Windows EXE build has not been executed here.

## Video workflow

1. Open the ORIGINAL product video in Video loop studio.
2. Click **Stabilization / Smart Aim / Background mask**.
3. Set the original background colour and the tracking rectangle. Preview the initial mask. The rectangle uses normalized X, Y, Width, Height (0–1), and should include the complete tool and its movement while excluding other large objects or a turntable if possible.
4. Enable position stabilization, Smart Aim Mask and/or background removal. Choose replacement colour or transparency.
5. Click **Preview initial mask / vertical aim**, adjust controls, then **Apply to all frames**. The job runs in the background with progress updates. Inspect playback across the video, not only frame 0.
6. Find loop points AGAIN on the processed footage. Previous candidates are cleared, because stabilization/masking changes image similarity. Compare candidates and refine endpoints as in v3.
7. Export the loop with your crop and logo. Solid-colour footage exports silent MP4; transparent footage exports silent ProRes 4444 MOV.

**Original / processed** toggles the preview and working clip for comparison. Loop candidates are cleared when switching, because they depend on which version you use. Switch back to processed before finding loop points and exporting effects. Opening another video does not replace the current one until decoding succeeds. Video-effect settings are saved separately in `%LOCALAPPDATA%\AtlasPhotoStudio\video-effects.json` after successful processing.

## Position stabilization

The app segments the target silhouette in proxy frames, estimates its centre through the clip, then smooths that trajectory. Corrections remove short position jitters while retaining deliberate product rotation. This is product-centric silhouette tracking rather than feature tracking on shiny rotating flutes.

Controls:

- **Strength:** 0–100% correction.
- **Smooth seconds:** temporal smoothing window, 0–2 seconds. Larger values remove slower position changes too.
- **Max shift:** bounds translation to a percentage of the image edge.
- **Safety crop:** optional 0–20% inset from every edge, scaled back to the output canvas. Use it to hide exposed correction borders. Default is zero to preserve framing; inspect cropping near the tool tip.

When keeping the original background, reflected edge filling is used outside the corrected frame. A safety crop can hide those areas. When removing the background, exposed edges use the selected replacement or transparency.

## Smart Aim Mask

Toggle **Smart Aim Mask** to establish an initial tool position and align the measured tool axis vertically in each frame. Smart Aim overrides standard centre smoothing.

The initial foreground silhouette supplies a reference centre and principal long axis. The app constructs a vertical target pose at that location; subsequent frame masks are compared by centre and axis, and a bounded rigid translation/rotation is applied. The tool's visible texture is not frozen, so its intended rotation is retained.

**Capture initial tool location** fills Target X/Y from the first frame. Leaving either coordinate at −1 uses the initial measured coordinate automatically. You can instead enter an explicit normalized target. The preview shows original, mask and vertical target.

**Max aim angle** limits angle correction; the default is 20 degrees and can be increased up to 60. **Smooth seconds** smooths the measured axis to reduce angle flicker. Short or round silhouettes have no reliable long axis, so angle correction is skipped. Maximum translation and strength still apply. Tight or inaccurate tracking rectangles can corrupt the pose; include the full relevant silhouette.

This corrects visible 2D lean/position wobble. It does not reconstruct perspective, recover hidden geometry or correct bent/out-of-round physical tools. Large 3D wobble and changing reflections may still be visible.

## Smart background mask

Masking runs locally for every frame with colour-seeded GrabCut segmentation, the chosen tracking region, the largest foreground component and the previous frame's mask as a segmentation hint. Interior silhouette holes are filled to preserve bright metal highlights.

Choose the **original background colour**, then adjust **colour tolerance** and **feather**. The default key is white, tolerance 35 (RGB-distance units), feather 1 proxy pixel. Feather is evaluated at proxy resolution and scaled into the processed output. Processing edge defaults to 1080, up to 2160; footage is not upscaled. Full source frames are used for output, with proxy-derived masks enlarged to match.

This works best with a plain contrasting background. It is not a general pretrained semantic cutout model: clutter, shadows touching the tool, similarly coloured metal/background, multiple objects, transparent objects and strong reflections may require better source footage or narrower settings. Largest-component selection can choose the wrong object if a turntable or prop dominates the region. Inspect the mask and output before publishing.

If tracking fails too often, processing stops. Background-removal output also stops if any frame loses the tool mask, rather than publishing a frame in which the tool disappears. Original files remain unchanged.

## Replacement colours and transparency

Use the colour picker or a #RRGGBB value for the replacement background. The choice affects the entire processed clip.

For **Transparent**, processed footage and final loops use **ProRes 4444 MOV with alpha**. The checkerboard is only a preview aid and is not encoded. Logo overlay is applied without flattening the alpha channel. Export verifies the frame count, and synthetic tests decode the resulting alpha both with and without a logo.

Standard H.264 MP4 does not carry this alpha output. Transparent MOV is a large editing/master file, and transparency support depends on the destination player/platform. For a normal Shopify product video, use a solid background MP4 unless you have separately verified support for your intended transparent workflow.

The complete processed clip lives in temporary storage and is removed on close/replacement. Export the final loop before closing. Normal MP4 processing adds an intermediate high-quality encode; MOV processing uses ProRes. The loop report records effect settings, tracked/interpolated frame counts and the original source path. All audio is removed as before.

## Validation

See VALIDATION.txt. Automated tests include known jitter reduction, vertical rigid alignment, translation limits, highlight-preserving segmentation, background-colour replacement, actual ProRes alpha decoding and alpha-preserving logo export. Existing photo, crop and loop-export tests also run. Windows-native rendering, EXE packaging and effects on your actual tool recordings still require local review.

Technical references:

- OpenCV segmentation: https://docs.opencv.org/4.x/d8/d83/tutorial_py_grabcut.html
- FFmpeg ProRes alpha encoding: https://ffmpeg.org/ffmpeg-codecs.html
