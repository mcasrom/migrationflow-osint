"""Genera claves VAPID para Web Push e imprime líneas para .env.

Uso:  python scripts/gen_vapid.py   (instala py-vapid si falta)
"""
import base64


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def generate() -> tuple[str, str]:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
    except ImportError:
        raise SystemExit("Falta cryptography: pip install cryptography")
    key = ec.generate_private_key(ec.SECP256R1())
    priv = key.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    pub = key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    return _b64url(priv), _b64url(pub)


if __name__ == "__main__":
    priv, pub = generate()
    print(f"VAPID_PRIVATE_KEY={priv}")
    print(f"VAPID_PUBLIC_KEY={pub}")
    print("VAPID_SUBJECT=mailto:migrationflow@viajeinteligencia.com")
    print()
    print("# Añade estas tres líneas a tu .env")
