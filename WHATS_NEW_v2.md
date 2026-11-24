# Atlas Photo Studio 2.0

## Upgrade

Extract this updated package into a new folder and double-click **START.bat**. It uses the same saved settings/credentials location as version 1. Existing upload history is retained. The launcher installs the additional image-processing dependency automatically, including when upgrading an existing environment.

**Save defaults** now works even before a logo is chosen. Your Shopify domain also saves automatically when edited and when you close the app. Credentials remain separate in Windows Credential Manager if you chose secure saving.

## Faster previews

The app creates bounded, cached image proxies and renders previews on a background worker. JPEGs use reduced-resolution decoding when supported. Changing logo position does not reload the full original. Stale preview results are discarded, and rapid changes cancel queued work.

Set **Logo / Mainshot crop / Export & preview → Export & preview → Preview edge px** to 360, 540, 720 or 1080. Start at 540 for a slower computer. Default 720. These settings affect the in-app preview only. The export reads the source again and uses the configured output resolution and quality. The transparent checkerboard is a display aid and is never exported.

Preview colour is approximate for speed; full exports continue to use sRGB conversion. The cached proxy limit is bounded to 24 images and 16 composed backgrounds, with source metadata and logos cached separately. Corrupt or unsupported files are reported.

## Logo X/Y pixels

In the **Logo** tab, set **X px** and **Y px**. The origin `(0,0)` is the image's top-left; the coordinates locate the logo's top-left. Presets place the logo on edges or at the centre. Click or drag the preview to position it.

Coordinates refer to the output canvas after cropping/resizing/padding, before a possible final size-limit reduction. If the file-size target forces the complete image to shrink, the logo scales along with it. Coordinates outside the available area are clamped so the logo fits. Different image shapes can therefore clamp to different actual positions.

Logo width and opacity retain their percentage controls. Version 1's percentage position/margin settings are replaced with pixel coordinates, initially X=32/Y=32. Review and save your preferred placement. Other compatible version 1 defaults migrate automatically.

## Filename and alt-text blocks

Click **Configure filename & alt-text blocks** below the photo list. There are independent tabs for filenames and Shopify alt text.

Add, remove, reorder or disable:

- **Basic name:** the product/export name at the top of the workspace.
- **Custom text:** add any prefix/postfix text. Its position in the list determines where it appears.
- **Sequence:** 01, 02, 03, etc.
- **View:** each selected photo's editable view label.

Edit the separator between blocks. The dialog shows examples; the workspace shows the current image's proposed filename and alt text. Apply and save naming defaults to reuse them.

Example blocks: `[Atlas Tools] [Basic name] [ZrN] [View]`. An example result is `Atlas Tools - TCT Router Bit 3F 8x22 - ZrN - Top - MAINSHOT CLOSEUP.png` for the first image. Avoid adding the brand/coating twice if they are already in the basic name.

The mainshot suffix is always enforced at the end of the first image's filename and alt text, including when names are long. Filename characters unsafe on Windows are replaced. If blocks generate repeated filenames, a sequence suffix prevents overwrites. Alt text follows its own blocks and is not modified for filesystem restrictions. Default filename and alt blocks are identical.

## First image: transparent MAINSHOT CLOSEUP

The **first included photo** is exported as the transparent mainshot and occupies position 1 in Shopify. It counts as one of the maximum five images. Other photos follow the normal JPEG/PNG export settings.

1. Select the best tool-tip photo and move it above the other included photos.
2. Click **Edit mainshot crop**. This selects the mainshot and displays the original photo at reduced preview resolution.
3. Drag a rectangle around the cutting end/top of the tool. Alternatively, enter **Left, Top, Width, Height** in the **Mainshot crop** tab and click **Apply pixel crop**. These four fields use the oriented SOURCE photo's pixels, unlike the logo controls which use the OUTPUT canvas pixels.
4. Click **Show finished preview** to inspect the crop and transparent background.
5. Adjust white threshold/feather if required, review the image, then export.

The initial crop is the source image's top 55%, not an AI prediction of where the cutting tip is. For sideways, rotated or unusually framed tools, place the crop manually. Crop settings are tracked per source path and are included when you explicitly save defaults. Changing which photo is first changes which photo receives the mainshot treatment.

The mainshot is always PNG, even when other images export as JPEG. Square WHITE padding is deliberately bypassed for the mainshot so transparency is retained. The crop rectangle determines its aspect ratio. The mainshot logo defaults to **No**; switch **Add logo to mainshot** to **Yes** if wanted. Mainshot filename and alt text always finish with **MAINSHOT CLOSEUP**.

### White-background removal

White removal runs locally without Shopify, paid AI, or an external upload. It selects near-white, neutral areas connected to an image edge, with a feathered transition and white-matte cleanup. Existing transparency is preserved. Enclosed white highlights inside a tool are left intact rather than making every white pixel transparent.

**White threshold** defaults to 235 (range 180–254). Lower values include more light-grey background, but can remove more pale tool detail. **Feather range** defaults to 15 (range 1–50). Higher values make the transition softer; for a grey background at the threshold, reducing the feather may help it become transparent.

This is white-background keying, not semantic object segmentation. It works best with clean white backgrounds and a clear edge. It does not remove complex/coloured backgrounds or enclosed white holes, and very pale metal edges connected to the background can be affected. Inspect polished tools on the checkerboard before uploading. Original photographs are never changed.

## Appearance

The workspace now uses Atlas Tools' black/charcoal panels, white text, stronger headings, and the website's #f5a900 gold for tabs, buttons and highlights. The UI uses native desktop typography so it does not require web fonts or a browser.

## Shopify behavior

The app continues to attach photos to an EXISTING selected Shopify product. It does not create new product listings. The first image becomes the main image; old product photos are kept after the new set. Existing connection, approval, upload ledger, retry and media-order checks remain in place. Source metadata/settings/naming changes require re-export before upload.
