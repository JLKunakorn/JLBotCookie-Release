"""Generate an Ed25519 keypair for the license server.

Install dependency first:
    pip install cryptography
"""

from base64 import b64encode

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> None:
    private_key = Ed25519PrivateKey.generate()
    private_pkcs8 = private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    print("Worker secret PRIV_PKCS8_B64:")
    print(b64encode(private_pkcs8).decode("ascii"))
    print()
    print("Client public_key_hex:")
    print(public_raw.hex())
    print()
    print("Commands:")
    print("wrangler secret put PRIV_PKCS8_B64")
    print("wrangler secret put ADMIN_TOKEN")


if __name__ == "__main__":
    main()
