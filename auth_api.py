"""Google sign-in service for the Domain Workbench backend.

POST /auth/google  — exchange a Google ID token for this app's own session JWT.
GET  /auth/me      — returns the signed-in user, given that session JWT.

Run with: python auth_api.py  (serves on port 8089)
"""
from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from auth_utils import mint_app_jwt, require_auth, verify_google_id_token

app = FastAPI(title="Auth API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GoogleLoginRequest(BaseModel):
    id_token: str


@app.post("/auth/google")
def google_login(body: GoogleLoginRequest):
    idinfo = verify_google_id_token(body.id_token)
    email = (idinfo.get("email") or "").lower()
    name = idinfo.get("name", "")
    picture = idinfo.get("picture", "")
    token = mint_app_jwt(email, name, picture)
    return {"token": token, "email": email, "name": name, "picture": picture}


@app.get("/auth/me")
def me(user: dict = Depends(require_auth)):
    return {"email": user["sub"], "name": user.get("name", ""), "picture": user.get("picture", "")}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8089)
