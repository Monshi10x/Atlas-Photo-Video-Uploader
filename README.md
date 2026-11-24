# Atlas Tools Photo & Video Studio 6.0 — Windows

## Install or upgrade

1. Extract the ZIP into a normal folder. Do not run from inside the ZIP.
2. Install Python 3.11 or newer from https://www.python.org/downloads/windows/ if needed. Include the Python launcher and Tcl/Tk components (defaults in the full installer).
3. Double-click **START.bat**. It creates/updates a private environment and installs requirements. Internet is needed for setup.
4. Your existing saved settings, credentials and upload history are reused. No source photos are overwritten.

This is the runnable desktop app and Python source, not a prebuilt EXE. **BUILD_EXE.bat** can package an EXE on Windows after setup; this packaging step has not been run here.

## What's new and how to use it

Read **WHATS_NEW_v6.md** for robust multi-band tracking, captured reference geometry masks, Hybrid mode, continuous subpixel rendering and a fixed vertical second pass.

Read **WHATS_NEW_v5.2.md** for the second pass on completed first-pass footage, residual-jitter controls and pass comparison. Read **WHATS_NEW_v5.1.md** for precision shaft lock, the supplied MVI_5090 settings and before/after video. Read **WHATS_NEW_v5.md** for the shared photo/video colour editor, presets and automatic importable settings sidecars. Read **WHATS_NEW_v4.md** for stabilization, Smart Aim Mask and video background masking/transparent export. Read **WHATS_NEW_v3.md** for the numbered workflow, aspect-locked crop handles and the new video-loop editor. **WHATS_NEW_v2.md** covers naming blocks, pixel logo coordinates, transparent-background removal and cached previews.

### Typical batch

1. **Add edited photos** or **Add folder** for one product.
2. Connect Shopify in **Connections & setup**, then search/select the product in step 1 at the top of **Photo workspace**. Or enter the basic name manually for export-only work.
3. Click **Suggest 5 locally** or **AI: choose angles**, then review selected views. Double-click rows to include/exclude. Use the arrows to order them and edit their view labels.
4. The first included photo is the transparent mainshot. Click **Edit mainshot crop**, draw a rectangle around the cutting end, then **Show finished preview**. Use the **Mainshot crop** tab for source-pixel crop fields and white-removal settings. Default aspect is 1:1. Drag corners to resize, drag inside to move, or choose Freehand for an unlocked rectangle.
5. In **Logo**, choose a transparent PNG logo and set **X px/Y px**, size and opacity. Logo X/Y=0/0 is the top-left. The first image's logo is off by default; enable it in Mainshot crop if wanted.
6. Click **Configure filename & alt-text blocks** to add/remove/reorder/disable custom prefixes, basic name, sequence, view and postfix blocks. Save your defaults. The mainshot always ends with **MAINSHOT CLOSEUP** in both names.
7. Click **Export selected** and review the actual files using **Open exports**. First image is always transparent PNG; other images follow export settings.
8. Click **Approve & upload** to attach the batch to the selected existing Shopify product. It shows the product/store before publishing. Existing images are retained after the new images. This app does not create product listings.

## Settings

**Save defaults** stores logo, naming, crop and export settings even if a logo has not been chosen yet. Shopify domain saves automatically on edit/close. Non-secret settings/history live in `%LOCALAPPDATA%\AtlasPhotoStudio`. Credentials remain in memory unless you choose secure saving to Windows Credential Manager.

Choose **step 6 → Preview px** (360/540/720/1080) for lower-resolution, cached previews. Export quality is independent. JPEG quality starts at 92 and the default size target is below 2 MB. If quality compression is insufficient, output dimensions decrease. PNG preserves transparency; other-image JPEG exports flatten onto white. Square white padding applies only to other images.

Exports go into a new batch subfolder. `manifest.json` contains names, alt text, local source paths, dimensions, byte counts and checksums; remove the manifest before publicly sharing a folder if those local paths should stay private. It contains no tokens or client secrets.

## Shopify setup

1. Open https://dev.shopify.com/dashboard. Create an app in the **same organization as your store**.
2. App URL: `https://shopify.dev/apps/default-app-home`; disable embedding. No redirect URL is needed for this organization's client-credentials connection.
3. Set Admin API scopes: `read_products,write_products,read_files,write_files`.
4. Release the app version and install it on Atlas Tools.
5. In the Shopify app's **Settings → Credentials**, find Client ID and Client secret.
6. In Photo Studio **Connections & setup**, enter your permanent `your-store.myshopify.com` domain, Client ID and Client Secret. Click **Get / refresh 24-hour access token**. Refresh again after expiry. Or paste an existing valid Admin API access token with the required scopes.
7. In **Photo workspace**, step 1, search by product title or `sku:YOUR-SKU`, then explicitly select the correct product. At most 30 search matches are displayed; narrow the search when needed.

If `shop_not_permitted` appears, verify the app and store are in the same Shopify organization. This desktop package does not include third-party public-app OAuth distribution. Shopify CLI automation tokens/Storefront tokens do not work as Admin API tokens.

**Save credentials securely** is optional and uses Windows Credential Manager. **Forget saved credentials** removes them. Do not paste credentials into screenshots or share them with other users.

### Upload recovery

The app stages binary files, attaches them with alt text, waits for image processing and verifies media order. A local success ledger prevents repeated attachments of the same file/alt/product combination on this PC. Existing images remain after the new batch; variant-specific image assignment is not implemented.

After an interrupted upload, some images may already be live. Check the error and Shopify before retrying. Previously recorded successful images are skipped. A matching alt text without a ledger record is treated as ambiguous and stops the batch. Writes are not retried automatically after timeouts. New exported content is a new batch; remove superseded images manually after review. Copying exports to another computer does not copy the upload ledger.

## Local versus AI photo selection

Local selection ranks sharpness/exposure and visual variety, excludes exact file duplicates and requires no cloud key. It cannot reliably understand router-bit geometry.

AI selection requires a separately billed OpenAI API key, configured in Connections. Only clicking AI selection sends the product name and up to 24 shortlisted compressed photo previews to OpenAI. Default vision model is `gpt-4.1-mini`, editable. AI chooses up to five distinct useful views and suggested labels; always review tool features before publishing. Batches above 24 unique images are shortlisted locally first. A ChatGPT subscription does not supply API credit.

Normal preview, local selection, crop, white removal and export run locally.

## Watch folder

Set a folder in Connections and enable watching while the app is open. It checks every 2.5 seconds and waits for stable size/modification time across scans. Scanning is non-recursive and includes existing files on first scan. Use one product per batch; never choose the export directory as the watched input. Watching adds photos for review; selection/export/upload still require clicks.

Very slow copying can defeat stability detection. Remove and manually re-add any changed photo already in the list. The app installs no background Windows service.

## Supported images and background removal

Photos: JPEG, PNG, TIFF, WebP, BMP. Export HEIC/RAW to one of these formats first. Logos: transparent PNG recommended; SVG/PDF logos must be converted to PNG first.

White removal is local, edge-connected white keying, not semantic segmentation. It preserves enclosed highlights and existing transparency but cannot guarantee perfect edges on white/polished metal, complex backgrounds or enclosed white holes. Inspect the mainshot on the checkerboard and adjust threshold/feather before upload. Original photographs are preserved. Full exports apply orientation and sRGB conversion; previews use approximate colour for speed.

## Validation and troubleshooting

See **VALIDATION.txt**. Run `.venv\Scripts\python.exe -m unittest discover -s tests -v` for automated tests. Linux virtual-display smoke tests exercised the native UI, preview, crop, naming dialog, export and settings persistence. Windows-native rendering, EXE building, live Shopify uploads and paid AI calls remain untested with your credentials.

If setup fails, read the error in START.bat. If Tcl/Tk is missing, reinstall full Python including Tcl/Tk. Preserve `%LOCALAPPDATA%\AtlasPhotoStudio` to retain settings and duplicate-upload history.

Official references:

- https://help.shopify.com/en/manual/products/product-media/product-media-types
- https://shopify.dev/docs/apps/build/dev-dashboard/create-apps-using-dev-dashboard
- https://shopify.dev/docs/apps/build/authentication-authorization/client-credentials-grant
- https://developers.openai.com/api/docs/guides/images-vision?api-mode=chat
