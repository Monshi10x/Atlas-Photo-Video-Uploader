# Atlas Photo & Video Studio 3.0

## Upgrade

Extract the ZIP into a new folder and run **START.bat**. The launcher installs the video dependency and its Windows FFmpeg binary automatically. You do not need a separate FFmpeg installation. Saved settings/credentials/upload history remain in the same location. EXE building is still optional using BUILD_EXE.bat and has not been run in this Linux environment.

## Photo workspace: numbered containers

The workspace is grouped into six steps:

1. **Match the Shopify product** — search/select at the very top of the workspace. Credentials remain in Connections & setup. Export-only work can use a manually entered basic name without connecting Shopify.
2. **Import, select & order photos.**
3. **Build filenames & alt text.**
4. **Frame the transparent mainshot.**
5. **Place the Atlas logo.**
6. **Export, review & upload.**

The Connections and Video tabs also group their controls into numbered containers.

## Aspect-locked mainshot crop

In step 4 choose **Edit mainshot crop**. The aspect selector defaults to **1:1**. Available options:

- 1:1
- 4:3
- 3:2
- 16:9
- 9:16
- **Freehand** (unlocked rectangle)

Gold squares mark the four corner handles. Drag a corner to resize while preserving the chosen aspect ratio. Drag inside the rectangle to move it without changing size. Drag outside the current rectangle to draw a new one. Crop coordinates are clamped to the source image boundary. Rectangles cannot extend outside the photograph.

The lock is calculated in source-image pixels, so 1:1 means a square image even when the source is portrait. Pixel-field edits also respect the active aspect. Switching aspect fits the new ratio inside the current box. **Reset** starts from the top 55% of the source, fitted to the chosen ratio. For sideways tools, position the box manually.

Existing saved rectangular crops are fitted to the active aspect. Choose Freehand to retain an unconstrained crop. Mainshots retain transparent PNG export and the mandatory MAINSHOT CLOSEUP suffix.

## Video loop studio

This is a local temporal-trimming, spatial-cropping and logo-overlay workflow for short rotating-product videos. It exports a new MP4 on your PC; it does not upload video to Shopify automatically.

### 01 / Open video & find a rotation

Open a product clip, usually your 30-second rotating-tool recording. Supported containers include MP4, MOV, M4V, AVI, MKV and WebM if the bundled FFmpeg build can decode their codecs.

The app creates low-resolution frame proxies in a temporary disk cache. Source clips must be 0.5–90 seconds, with a readable frame rate of 1–120 fps. The working grid preserves the reported frame rate up to 60 fps; higher-rate clips use a 60 fps grid. Variable-frame-rate footage is normalized to this constant frame grid. Frame indices displayed by this app refer to that grid, not necessarily the source container's original frame numbers/timestamps. Preview, matching and export use the same grid.

Set **Target seconds** to about **7**, and **Search ± seconds** to, for example, **1.5**. The search checks plausible rotations between about 5.5 and 8.5 seconds and searches across the source clip for clean matching phases. Tick **Keep current start frame** to search only for an endpoint corresponding to your chosen starting frame.

Click **Find best loop points**. Matching uses image detail/gradients, a short neighborhood of frames around each boundary, and a motion-continuity penalty. Static segments are rejected. It returns several possible joins, not a guarantee of a perfect full revolution.

### 02 / Compare candidates

Select a candidate from the list. It sets the start frame and matching return frame. Lower error means a closer feature/motion match within this clip; the number is not a universal confidence percentage.

Symmetrical/fluted tools can repeat visually partway around a revolution. Choose a target/tolerance around the real rotation period, inspect distinct marks/reflections, and compare candidates. Camera shake, variable turntable speed, lighting flicker and occlusion can prevent a completely seamless loop. The app cannot invent a true perfect join when the recording does not contain one.

### 03 / Check the join

The comparison shows:

- **Start (included)** — the loop's first frame.
- **Return (excluded)** — the later frame which matches the first.
- **Difference ×4** — an amplified visual difference, useful for seeing small misalignment.

Use the **−1 / +1** buttons beside either frame number for frame-level refinement. You can also type exact frame indices. **Play across join** repeats the last 12 frames followed by the first 12 frames (or fewer for very short loops), making a jump easier to spot. **Play whole loop** previews the full selected interval. **Stop / compare** returns to the side-by-side view. Playback is a low-resolution approximation at up to 30 display updates per second; export retains the working frame rate.

The return frame is deliberately EXCLUDED. If frames 42 and 252 match, export is frames **[42,252)**: 210 frames. This avoids holding the same orientation twice at the join. At 30 fps that is exactly 7 seconds. Comparing a matching start/end still is not enough on its own; check the motion across the join too.

### 04 / Crop, brand & export MP4

Optional spatial-crop fields (**X, Y, Width, Height**) use source-video pixels after orientation. They default to the complete frame. Crop placement is numeric; the video's spatial crop does not use the photo tab's drag handles. Candidate matching uses the source frame, while comparison/playback previews apply your spatial crop and logo.

The default logo is the image selected in Photo workspace, step 5. Video logo controls have separate X/Y (output pixels), width percentage and opacity. Disable **Add default Atlas logo** to export without it. Preview includes the selected logo. Invalid crop fields must be fixed before export.

**Output edge px** defaults to 1080. The app preserves aspect ratio, avoids upscaling, and rounds output dimensions to even numbers for MP4 compatibility. X/Y logo positions are clamped inside that final output canvas. Previews are approximate; inspect the exported video.

Click **Export looping MP4** and choose a NEW filename. Export uses H.264, high-quality CRF 18, YUV420p and fast-start metadata. **Audio is removed** so a background recording does not create an audible loop discontinuity. No crossfade is applied to hide motion errors.

The app re-encodes from the source, trims at the selected working-grid frames, applies crop/logo, and decodes the result to verify the exact frame count before publishing it to your output path. Source files and existing output files are never overwritten. A changed source must be reopened and reanalyzed.

A matching `.loop.json` file records the source path, frame interval, FPS, output dimensions, duration and error metric. This includes local source paths; remove that report if publicly sharing only the MP4.

Temporary preview caches are removed on normal close or when replacing a loaded clip. A forced process termination can leave temporary files in the operating system's temporary directory.

## Validation and limits

See VALIDATION.txt. Tests include aspect geometry, source-pixel square crops, moving/resizing at boundaries, a generated periodic rotation, automatic loop-point detection, exact exclusive-end frame export, spatial crop, logo overlay and protecting existing files. Native Tk UI smoke checks run under a Linux virtual display. Windows-specific rendering and EXE packaging remain untested. Real-world loop quality still needs review on your own footage. Existing live Shopify credentials/uploads were not exercised while developing this update.

FFmpeg trim and overlay reference: https://ffmpeg.org/ffmpeg-filters.html
