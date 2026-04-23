# TrackCam Viewer — GCP Setup Guide

## 1. Install Prerequisites

### gcloud CLI
Download and run the installer from https://cloud.google.com/sdk/docs/install  
After installation, open a new terminal and verify:
```
gcloud --version
```

### Terraform (>= 1.5)
Download from https://developer.hashicorp.com/terraform/downloads  
Extract the binary and add it to your PATH. Verify:
```
terraform --version
```

### Docker Desktop
Download from https://www.docker.com/products/docker-desktop  
Make sure it is running before building images.

### Node.js 20+
Download from https://nodejs.org/en/download  
Verify:
```
node --version   # should be 20.x or higher
```

---

## 2. Authenticate gcloud

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project trackcam-viewer
```

If the project does not exist yet:
```bash
gcloud projects create trackcam-viewer --name="TrackCam Viewer"
```

Enable billing in the Cloud Console:
https://console.cloud.google.com/billing/linkedaccount?project=trackcam-viewer

---

## 3. Configure OAuth Consent Screen (one-time, manual)

These steps cannot be automated with Terraform.

1. Go to https://console.cloud.google.com/apis/credentials/consent?project=trackcam-viewer
2. Select **External** user type, click **Create**
3. Fill in:
   - App name: `TrackCam Viewer`
   - User support email: `dabearic@gmail.com`
   - Developer contact: `dabearic@gmail.com`
4. Click through Scopes and Test Users steps (no changes needed yet)
5. Click **Save and Continue** through to the end

Then create an OAuth 2.0 client:

1. Go to https://console.cloud.google.com/apis/credentials?project=trackcam-viewer
2. Click **+ Create Credentials** → **OAuth client ID**
3. Application type: **Web application**
4. Name: `TrackCam Web`
5. Leave Authorized origins/redirects blank for now (you will add the Cloud Run URL after deploy)
6. Click **Create** — note the **Client ID** and **Client Secret**

---

## 4. Enable Identity Platform Google Sign-In (one-time, manual)

1. Go to https://console.cloud.google.com/customer-identity/providers?project=trackcam-viewer
2. Click **Add a provider** → **Google**
3. Paste the Web Client ID and Client Secret from step 3
4. Click **Save**
5. Copy the **API Key** and **Auth Domain** shown on the Identity Platform overview page —
   you will need these in step 8 (frontend config)

---

## 5. Request GPU Quota

Cloud Run GPU requires a quota increase on new projects.

1. Go to https://console.cloud.google.com/iam-admin/quotas?project=trackcam-viewer
2. Filter for: `NVIDIA_L4_GPU` in region `us-east4`
3. Select it and click **Edit Quotas** → request a limit of **1**
4. Submit — approval usually takes a few minutes to a few hours

---

## 6. Deploy Infrastructure with Terraform

```bash
cd infra/terraform

# Copy and fill in the variables file
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars — add your oauth_client_id and oauth_client_secret

terraform init
terraform plan    # review what will be created
terraform apply   # type 'yes' to confirm
```

Note the outputs — you will need:
- `api_url` — the Cloud Run service URL
- `bucket_name` — the GCS bucket name
- `artifact_registry` — the Docker registry URL

---

## 7. Add Cloud Run URL to OAuth Client (manual, post-deploy)

After `terraform apply` prints the `api_url`:

1. Go back to https://console.cloud.google.com/apis/credentials?project=trackcam-viewer
2. Click the OAuth client you created in step 3
3. Under **Authorized JavaScript origins** add: `https://<your-api-url>`
4. Under **Authorized redirect URIs** add: `https://<your-api-url>`
5. Click **Save**

Also add the domain to Identity Platform:
1. Go to https://console.cloud.google.com/customer-identity/settings?project=trackcam-viewer
2. Under **Authorized domains** add your Cloud Run URL (without `https://`)

---

## 8. Configure Frontend Firebase Settings

Edit `webapp/frontend/src/firebase.js` and fill in the values from step 4:

```js
const firebaseConfig = {
  apiKey:     "AIza...",          // from Identity Platform overview
  authDomain: "trackcam-viewer.firebaseapp.com",
  projectId:  "trackcam-viewer",
}
```

---

## 9. Build and Push Docker Images

Configure Docker to push to Artifact Registry:
```bash
gcloud auth configure-docker us-east4-docker.pkg.dev
```

Build and push the web API image:
```bash
cd infra
docker build -f Dockerfile -t us-east4-docker.pkg.dev/trackcam-viewer/trackcam/api:latest ../
docker push us-east4-docker.pkg.dev/trackcam-viewer/trackcam/api:latest
```

Build and push the inference job image (this is large — ~8 GB — allow 15-30 minutes):
```bash
docker build -f Dockerfile.inference -t us-east4-docker.pkg.dev/trackcam-viewer/trackcam/inference:latest ./inference
docker push us-east4-docker.pkg.dev/trackcam-viewer/trackcam/inference:latest
```

---

## 10. Deploy Cloud Run Service

After pushing images, re-run Terraform to update the Cloud Run service with the new image:
```bash
cd infra/terraform
terraform apply
```

Or trigger a new revision directly:
```bash
gcloud run services update trackcam-api \
  --image us-east4-docker.pkg.dev/trackcam-viewer/trackcam/api:latest \
  --region us-east4
```

---

## 11. Open the App

Get the URL:
```bash
terraform output api_url
```

Open it in your browser and sign in with your Google account.

---

## Local Development

The local backend (`webapp/backend/main.py`) continues to work as before — it does not
require any GCP services. Run it with:
```bash
cd webapp/backend
pip install fastapi uvicorn
python main.py
```

The cloud backend (`webapp/backend/main_cloud.py`) requires GCP credentials:
```bash
gcloud auth application-default login
export GCS_BUCKET=trackcam-viewer-data
export GCP_PROJECT=trackcam-viewer
export INFERENCE_JOB_NAME=projects/trackcam-viewer/locations/us-east4/jobs/speciesnet-inference
```
