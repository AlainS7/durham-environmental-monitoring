# 🔐 Oura Pipeline Secrets - Quick Setup

## ✅ What You've Already Set Up

1. ✅ **Pre-commit hook** - Installed at `.git/hooks/pre-commit`
   - Prevents accidental commits of token files
   - Checks for credentials in staged changes
   - Blocks data files from being committed

2. ✅ **Safe code structure** - No hardcoded secrets anywhere

## 📝 What You Need to Set Up

### For Each Oura Ring User/Resident

You need **one Personal Access Token per person** whose Oura data you're collecting.

**How to get them:**
1. Each participant logs into https://cloud.ouraring.com
2. Goes to "Personal Access Tokens" (top-right menu)
3. Clicks "Create a new personal access token"
4. Copies the token (looks like: `ABCD1234EFGH5678IJKL...`)
5. Sends it to you securely (NOT via email!)

---

## 🚀 Quick Start: Local Development

### Step 1: Create Token Files

```bash
# Create the secure directory (outside your repo)
cd /Users/alainsoto/Projects/Developer/work/github.com/AlainS7/
mkdir -p "Secure Files"

# Create one file per resident (example for 3 residents)
echo "PERSONAL_ACCESS_TOKEN=paste_token_1_here" > "Secure Files/pat_r1.env"
echo "PERSONAL_ACCESS_TOKEN=paste_token_2_here" > "Secure Files/pat_r2.env"
echo "PERSONAL_ACCESS_TOKEN=paste_token_3_here" > "Secure Files/pat_r3.env"
```

### Step 2: Update Config

Edit `oura-rings/oura_import_options.py`:

```python
RESIDENTS_TO_PROCESS = [1, 2, 3]  # Match the residents you created files for
OPTIONS["export_to_bigquery"] = False  # Start with False for local testing
```

### Step 3: Test It!

```bash
cd durham-environmental-monitoring
python -m oura_rings.cli --residents 1 --dry-run
```

Expected: ✅ Data fetched, files saved locally

---

## ☁️ Production: Google Cloud Setup

### Required Secrets in Google Secret Manager

```bash
# Set your project
export PROJECT_ID="durham-weather-466502"

# Create one secret per resident
echo -n "actual_token_for_resident_1" | \
  gcloud secrets create oura-pat-r1 --data-file=- --project=$PROJECT_ID

echo -n "actual_token_for_resident_2" | \
  gcloud secrets create oura-pat-r2 --data-file=- --project=$PROJECT_ID

# Repeat for each resident...
```

### Required Secrets in GitHub (for Actions)

Go to: https://github.com/AlainS7/durham-environmental-monitoring/settings/secrets/actions

Add these secrets:

| Name | Value | Where to Get It |
|------|-------|----------------|
| `GCP_PROJECT_ID` | `durham-weather-466502` | Your GCP project ID |
| `GCP_SA_KEY` | `{...json...}` | See "Get Service Account Key" below |
| `BQ_DATASET` | `oura` | Your choice (dataset name) |
| `OURA_PAT_R1` | `token_1` | From each participant's Oura account |
| `OURA_PAT_R2` | `token_2` | From each participant's Oura account |
| `OURA_PAT_R3` | `token_3` | From each participant's Oura account |

### Get Service Account Key

```bash
# Create service account for GitHub Actions
gcloud iam service-accounts create github-actions-oura \
  --display-name="GitHub Actions - Oura" \
  --project=$PROJECT_ID

# Get the email
SA_EMAIL="github-actions-oura@${PROJECT_ID}.iam.gserviceaccount.com"

# Grant BigQuery permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/bigquery.dataEditor"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/bigquery.jobUser"

# Create key
gcloud iam service-accounts keys create /tmp/github-sa-key.json \
  --iam-account=$SA_EMAIL

# Copy contents to GitHub secret GCP_SA_KEY
cat /tmp/github-sa-key.json

# Delete local copy
rm /tmp/github-sa-key.json
```

---

## 🧪 Testing Checklist

- [ ] Local dry-run works: `python -m oura_rings.cli --residents 1 --dry-run`
- [ ] Local real fetch works: `python -m oura_rings.cli --residents 1`
- [ ] BigQuery dry-run works: `python -m oura_rings.cli --residents 1 --export-bq --dry-run`
- [ ] BigQuery real upload works: `python -m oura_rings.cli --residents 1 --export-bq --no-dry-run`
- [ ] Pre-commit hook blocks token files: Try `git add "Secure Files/pat_r1.env"`

---

## 🔒 Security Rules

**NEVER commit:**
- ❌ `pat_r*.env` files
- ❌ Actual token strings in code
- ❌ Service account JSON keys
- ❌ Data files (`.json`, `.csv`)

**ALWAYS:**
- ✅ Use `.env.sample` for examples (no real tokens)
- ✅ Store tokens outside the repo
- ✅ Use Secret Manager for production
- ✅ Keep `RESIDENTS_TO_PROCESS = []` empty in the repo

---

## 📚 Full Documentation

See `SECRETS_SETUP.md` for complete details including:
- Cloud Run deployment
- GitHub Actions workflow examples
- Troubleshooting guide
- Production deployment checklist

---

## 🆘 Common Issues

**"No access token available"**
→ Check file exists: `ls "../../../../Secure Files/pat_r1.env"`
→ Check format: `cat "../../../../Secure Files/pat_r1.env"` should show `PERSONAL_ACCESS_TOKEN=xxx`

**"git commit blocked by pre-commit hook"**
→ Good! That means it's working. Remove the sensitive file from staging: `git reset HEAD <file>`

**"Permission denied" in BigQuery**
→ Run: `gcloud auth application-default login`
→ Set: `export BQ_PROJECT=durham-weather-466502`

---

## 📞 Need Help?

Check the full guide: `oura-rings/SECRETS_SETUP.md`
