# Warden showcase on Vercel

This deploys a static, credential-free visual walkthrough from `public/`.
It does **not** connect to Databricks, run migrations, or expose checkpoint
intent. The live proof remains the CLI demo and its recorded evidence.

## Fastest deployment

1. In Vercel, import `github.com/aditaro/cli` and select branch
   `vercel-showcase`.
2. In **Settings → Build and Deployment**, set **Root Directory** to `public`.
   Select framework preset **Other**; leave install/build commands unset.
   This is important: the repository root contains the Entire CLI's Go `api/`
   package, which Vercel would otherwise try to treat as serverless functions.
3. Deploy. The project URL is the shareable visual link.

For an existing Vercel project that is currently tracking `main`, first change
the production branch in **Settings → Git** to `vercel-showcase`, then make the
Root Directory change above and redeploy.

Or, from a local checkout with the Vercel CLI installed:

```bash
npx vercel --prod public
```

Before running Warden for real, use the operator preflight locally:

```bash
python3 -m pip install -r requirements.txt
python3 warden/preflight.py
python3 warden/preflight.py --live
```
