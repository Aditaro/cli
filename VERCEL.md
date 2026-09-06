# Warden showcase on Vercel

This deploys a static, credential-free visual walkthrough from `public/`.
It does **not** connect to Databricks, run migrations, or expose checkpoint
intent. The live proof remains the CLI demo and its recorded evidence.

## Fastest deployment

1. Push the `vercel-showcase` branch.
2. In Vercel, import `github.com/aditaro/cli` and select that branch.
3. Leave the project root as the repository root. Vercel reads `vercel.json`:
   no dependency install is required and `public/` is the output directory.
4. Deploy. The project URL is the shareable visual link.

Or, from a local checkout with the Vercel CLI installed:

```bash
npx vercel --prod
```

Before running Warden for real, use the operator preflight locally:

```bash
python3 -m pip install -r requirements.txt
python3 warden/preflight.py
python3 warden/preflight.py --live
```
