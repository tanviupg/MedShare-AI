# Local prescription image screening

The upload path can use OpenAI CLIP ViT-B/32 as a local, zero-shot image screen for
printed/handwritten prescription-like documents, dogs, cats, people, unrelated
documents, and unrelated objects. PaddleOCR remains a separate text extraction
step. Neither component verifies the prescriber or authenticity, and pharmacist
verification remains mandatory.

## Model and runtime

- Model: `openai/clip-vit-base-patch32` (ViT-B/32).
- Checkpoint: about 605 MB (`model.safetensors`); allow additional disk and RAM for
  PyTorch, Transformers, and the loaded model. CPU inference is supported; an
  NVIDIA GPU can improve throughput but is not required.
- The upstream OpenAI CLIP code repository is MIT-licensed. The model card describes
  CLIP as a research output and cautions against deployment without careful,
  task-specific evaluation. Use the configured thresholds conservatively and test
  with the actual prescription image mix before relying on it for rejection.
- PyTorch currently supports Python 3.14 on Windows, but the existing pinned
  PaddleOCR/PaddlePaddle packages may have narrower Python support. Keep the
  classifier dependency set optional and use a Python version compatible with all
  backend packages in the deployment environment.

No model weights are downloaded by the app at request time. Classification is required
for image uploads. If the classifier is disabled, its dependencies are absent, or its
local model cannot load or run, the API returns HTTP 503 and does not store the file or
create a request. PDFs continue through the existing pharmacist review flow because
PDF rendering is not configured.

## Local setup

From the repository root, install the optional dependencies in the backend
environment (choose the CPU or CUDA PyTorch wheel matching the host):

```powershell
cd D:\newMed\backend
python -m pip install -r requirements-prescription-classifier.txt
```

Download the model deliberately; this transfers roughly 605 MB and stores it under
`backend\models`:

```powershell
hf download openai/clip-vit-base-patch32 --local-dir models/clip-vit-base-patch32
```

Configure the API process environment (the defaults below are enabled and point at
the local model directory):

```powershell
$env:PRESCRIPTION_IMAGE_CLASSIFIER_ENABLED = "true"
$env:PRESCRIPTION_IMAGE_CLASSIFIER_MODEL_PATH = "models/clip-vit-base-patch32"
```

Do not set `PRESCRIPTION_IMAGE_CLASSIFIER_ENABLED=false` for an API that accepts
prescription image uploads: that deliberately blocks those uploads with HTTP 503.

The model path must contain the Transformers CLIP processor and model files. The
service loads only from this local path (`local_files_only=True`); an absent model
does not trigger a network fetch.

## Practical real-image check

With the API running and classifier installed, submit representative images through
the Patient Dashboard or its existing prescription upload endpoint:

1. Test dog and cat photos, a people photo, and unrelated object/document photos.
   Clear high-confidence non-prescription classifications should return HTTP 422
   with a request to upload a valid doctor's prescription; no request or file should
   be created.
2. Test printed and handwritten prescriptions under typical lighting and rotation.
   They should proceed to the normal pending pharmacist review, never be approved
   automatically.
3. Test blurry, cropped, unfamiliar, and mixed-content images. Ambiguous results
   should remain pending review rather than being treated as verified.
4. Repeat the check with PaddleOCR unavailable. Classifier results still screen
   clear unrelated images; OCR failure by itself must not reject an image.

These are manual real-model checks and require the optional dependencies and downloaded
weights above. The automated mocked unit test exercises the rejection and pre-storage
ordering only; it does not demonstrate real CLIP model behavior. Record any false
rejects and adjust thresholds only after reviewing a representative test set. CLIP
scores are not calibrated probabilities.
