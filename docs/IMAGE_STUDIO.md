# Image studio

Open **http://127.0.0.1:8766/images** after starting
`python -m storyforge.production_web`. The production planner links to the studio.

## Models

The studio reads Vultr's live `/v1/images/models` catalog and caches it for
30 minutes. It does not silently rename an unavailable model or switch providers.
At implementation time, Vultr advertises **MOSS-Image** (`moss-image`), not a model
named "Muse Image". **Muse Glimmer** (`muse-glimmer-30b`) is the optional visual
prompt writer; it does not render image pixels. Select the actual image model in
the studio before generating. All image rendering goes through Vultr.

## Using it

1. Choose Character, Scene, Location, Prop/costume, Storyboard frame, or Anything
   else. Enter the subject and visual direction, or leave them blank to choose a
   central image from the loaded story.
2. Leave story context on for an adaptation. Turn it off for an unrelated custom
   image. Text prompts work without reference-image uploads.
3. Prepare an editable prompt. Muse Glimmer can write it from relevant story
   excerpts; disabling that option uses a local template without a model call.
4. Review or directly edit the final prompt. Select a Vultr image model, shape,
   resolution and count (default one, maximum four). Optional seeds and steps are
   checked against the model's advertised capabilities.
5. Click Generate images. If the prompt is empty, the app prepares one first.
   Each click can incur one prompt-writing call plus the selected image request.
6. View or download the result in Saved images. Reuse its prompt for another
   generation, or choose Use for location scouting to attach it to the production
   planner. Enter the actual filming region and build a plan to research matches.

The model catalog drives available shapes and size limits; invalid combinations
are removed before rendering. A gallery entry records the actual provider/model,
exact submitted prompt, dimensions, optional seed/steps and provider usage/cost.
A seed is best-effort reproducibility, not a guarantee of character identity.
MOSS-Image is text-to-image: uploaded reference-image editing, inpainting and
identity-locked variants are not part of this version. A storyboard request creates
one frame unless the prompt explicitly asks for a grid.

## Storage and API

The server uses `VULTR_INFERENCE_API_KEY` from its environment. It does not load
`.env` automatically, and no credentials are returned to the browser or written to
image manifests. The existing host/origin checks and local request token protect
the generation endpoints. Work runs in the existing single-worker queue to prevent
duplicate button presses or overlapping generation jobs.

Images are requested as base64 PNG and saved atomically in the selected story's
`images/` directory. Metadata is in `<id>.json`, images in `<id>-<index>.png`.
Saved files remain available across server restarts, without expiring provider URLs.
The gallery loads at most the latest 100 requests. These files may contain story
content and should only be committed or shared when intended.

Routes:

- `GET /images`: studio UI
- `GET /api/images/models`: live cached model catalog
- `POST /api/images/prepare`: asynchronous prompt preparation
- `POST /api/images/generate`: asynchronous image generation
- `GET /api/job/<id>`: job status / completed image ID or prepared prompt
- `GET /api/images`: saved gallery
- `GET /api/images/<id>`: generation metadata
- `GET /media/images/<id>/<index>.png`: saved PNG (`?download=1` for attachment)

There are no automatic paid retries or fallback models. On provider errors or
timeouts the failure is recorded. A timeout can leave provider billing uncertain;
check the gallery and provider usage before repeating. The provider response arrives
with completed images; progress text does not claim progressive image previews.
If the server restarts during a request, the saved manifest remains `generating`
with completion unknown; this version cannot resume an upstream synchronous call.

The location-planning handoff attaches one saved image in browser memory, without
re-uploading it manually or spending a SerpAPI search. Actual planning then sends
the image to Muse Glimmer. Images over the planner's 5 MB limit must first be
resized by the user. The generated image is a visual reference, not evidence of a
real location or filming permission.

## Verification

```powershell
python -m unittest tests.test_image_studio tests.test_production tests.test_soundtracks tests.test_api -v
```

Tests cover model caching, unsupported model names, subject retrieval, prompt
preparation, no-story custom requests, dimensions/count/seed/step validation,
provider failures without retries, saved PNG/provenance, path restrictions and the
HTTP generation-to-gallery flow. API tests require the API optional dependencies.

Provider reference: https://api.vultrinference.com/docs/reference/create-image
