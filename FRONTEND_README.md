# Constitutional AI Frontend

**Den enda frontend-appen för detta projekt.**

- **Sökväg:** `apps/konstitutionell-frontend/`
- **Stack:** React 19 + Vite 7 + TypeScript 5.9 + Three.js (R3F/Drei) + Tailwind CSS 4 + Zustand 5
- **Port:** 3003 (dev server)
- **Backend:** `VITE_BACKEND_URL` (default `http://localhost:8900`)

## Kommandon

```bash
cd apps/konstitutionell-frontend
npm install
npm run dev    # :3003
npm run build
npm run lint
```

## Viktigt

- Skapa **aldrig** nya frontend-appar eller använd Streamlit
- Ignorera `/frontend/` (finns inte, referenser är legacy)
- Se `CLAUDE.md` för full projektöversikt
