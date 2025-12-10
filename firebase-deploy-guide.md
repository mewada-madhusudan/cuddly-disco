# GitHub Actions Pipeline for Firebase Hosting

## Prerequisites

1. A Firebase project set up
2. Firebase CLI installed locally (`npm install -g firebase-tools`)
3. Your website code in a GitHub repository

## Step 1: Initialize Firebase in Your Project

If you haven't already, initialize Firebase in your local project:

```bash
firebase login
firebase init hosting
```

During initialization:
- Select your Firebase project
- Specify your build directory (e.g., `build`, `dist`, or `public`)
- Configure as a single-page app if needed

This creates a `firebase.json` and `.firebaserc` file in your project root.

## Step 2: Get Firebase Token

Generate a Firebase CI token for GitHub Actions:

```bash
firebase login:ci
```

Copy the token that's displayed. You'll need this for GitHub secrets.

## Step 3: Add GitHub Secrets

1. Go to your GitHub repository
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add the following secret:
   - Name: `FIREBASE_TOKEN`
   - Value: The token from Step 2

## Step 4: Create GitHub Actions Workflow

Create a file at `.github/workflows/firebase-deploy.yml` in your repository:

```yaml
name: Deploy to Firebase Hosting

on:
  push:
    branches:
      - main  # or master, depending on your default branch
  pull_request:
    branches:
      - main

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '18'  # Adjust to your Node version
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Build project
        run: npm run build

      - name: Deploy to Firebase
        uses: FirebaseExtended/action-hosting-deploy@v0
        with:
          repoToken: '${{ secrets.GITHUB_TOKEN }}'
          firebaseServiceAccount: '${{ secrets.FIREBASE_TOKEN }}'
          channelId: live
          projectId: your-firebase-project-id  # Replace with your project ID
```

## Alternative: Using Firebase Service Account (Recommended for Production)

For more secure deployments, use a service account instead of a token:

### 1. Create Service Account

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select your project
3. Go to **Project Settings** → **Service Accounts**
4. Click **Generate New Private Key**
5. Save the JSON file securely

### 2. Add Service Account to GitHub Secrets

Add a new secret named `FIREBASE_SERVICE_ACCOUNT` with the entire JSON content.

### 3. Updated Workflow with Service Account

```yaml
name: Deploy to Firebase Hosting

on:
  push:
    branches:
      - main

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '18'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Build project
        run: npm run build

      - name: Deploy to Firebase
        uses: FirebaseExtended/action-hosting-deploy@v0
        with:
          repoToken: '${{ secrets.GITHUB_TOKEN }}'
          firebaseServiceAccount: '${{ secrets.FIREBASE_SERVICE_ACCOUNT }}'
          channelId: live
```

## Common Configurations

### For Different Build Tools

**Vite:**
```yaml
- name: Build project
  run: npm run build
```

**Create React App:**
```yaml
- name: Build project
  run: npm run build
```

**Next.js (Static Export):**
```yaml
- name: Build project
  run: npm run build
```

### Preview Channels (for Pull Requests)

To deploy PR previews to temporary URLs:

```yaml
on:
  pull_request:
    branches:
      - main

jobs:
  build-and-deploy-preview:
    runs-on: ubuntu-latest
    steps:
      # ... same checkout, setup, and build steps ...
      
      - name: Deploy Preview
        uses: FirebaseExtended/action-hosting-deploy@v0
        with:
          repoToken: '${{ secrets.GITHUB_TOKEN }}'
          firebaseServiceAccount: '${{ secrets.FIREBASE_SERVICE_ACCOUNT }}'
          channelId: preview-${{ github.event.pull_request.number }}
```

## Step 5: Commit and Push

1. Commit your workflow file
2. Push to your main branch
3. GitHub Actions will automatically trigger and deploy to Firebase

## Verify Deployment

- Check the **Actions** tab in your GitHub repository to see the workflow progress
- Once complete, visit your Firebase Hosting URL to see the deployed site

## Troubleshooting

- **Build fails**: Check your build command and ensure all dependencies are in `package.json`
- **Deploy fails**: Verify your Firebase token/service account is correct
- **Wrong files deployed**: Check your `firebase.json` public directory matches your build output
- **Node version issues**: Update the `node-version` in the workflow to match your local environment