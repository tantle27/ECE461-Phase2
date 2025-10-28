# react-app

Local Vite + React app with Tailwind, routing, upload and search example pages.

Quick start:

1. cd into this folder

```powershell
Set-Location .\app\react-app
npm install
npm run dev
```

The app expects an API base URL in VITE_API_URL (optional). Create a `.env` file in this folder with:

VITE_API_URL=http://localhost:8000/api

Upload and Search pages call `/upload` and `/search?q=` respectively under that base URL if set.
