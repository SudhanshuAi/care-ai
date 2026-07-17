# Care AI Mock PMS Admin

Separate frontend for inspecting mock-PMS write-backs after voice bookings.
Open access — demo/seeded data only.

**Live:** [https://care-ai-pms.onrender.com/](https://care-ai-pms.onrender.com/)

## What it shows

- Appointment list with booking status and PMS sync status
- Detail panel with create / reschedule / cancel receipt timeline
- Retry button for `pending`, `pending_retry`, and `failed` syncs

## Local development

```bash
cd frontend
cp .env.example .env
# set VITE_API_BASE_URL=http://localhost:8000
npm install
npm run dev
```

Open http://localhost:5173.

## Backend requirements

On the API service set CORS for your frontend origin:

```env
CORS_ORIGINS=http://localhost:5173,https://care-ai-pms.onrender.com
```

No admin token is required for this demo console.

## Deploy on Render (Static Site)

1. New → Static Site
2. Root directory: `frontend`
3. Build command: `npm install && npm run typecheck && npm run build`
4. Publish directory: `dist`
5. Environment variable:
   - `VITE_API_BASE_URL=https://care-ai-backend-321k.onrender.com`
     (or your backend URL; no trailing slash)

After deploy, add the frontend URL to the backend `CORS_ORIGINS`
(for this deployment: `https://care-ai-pms.onrender.com`).
