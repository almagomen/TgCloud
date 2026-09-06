#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "google-auth-oauthlib>=1.4.1",
# ]
# ///
"""Script interactivo de autorización para la API de Google Drive.

Uso:
    uv run auth/auth_drive.py
"""

import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

SCOPES = ['https://www.googleapis.com/auth/drive']
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDS_FILE = os.path.join(PROJECT_ROOT, 'auth', 'credentials.json')
TOKEN_FILE = os.path.join(PROJECT_ROOT, 'auth', 'google_token.json')

def authenticate():
    if not os.path.exists(CREDS_FILE):
        print(f"\n❌ Error: No se encontró el archivo de credenciales en:\n   {CREDS_FILE}")
        return

    flow = InstalledAppFlow.from_client_secrets_file(
        CREDS_FILE,
        scopes=SCOPES,
        redirect_uri='http://localhost:8080/'
    )

    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')

    print("\n" + "="*70)
    print("🔐 AUTORIZACIÓN DE GOOGLE DRIVE (PEP 723)")
    print("="*70)
    print("\n1. Abre este enlace en tu navegador:\n")
    print(auth_url)
    print("\n" + "="*70)
    print("2. Copia la URL resultante completa de localhost:8080:")
    print("="*70 + "\n")

    redirect_response = input("Pega aquí la URL completa: ").strip()

    flow.fetch_token(authorization_response=redirect_response)
    creds = flow.credentials

    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes
    }

    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    with open(TOKEN_FILE, 'w') as f:
        json.dump(token_data, f, indent=2)

    print(f"\n✅ ¡Éxito! Token guardado en:\n   {TOKEN_FILE}\n")

if __name__ == '__main__':
    authenticate()
