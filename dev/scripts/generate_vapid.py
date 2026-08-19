
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
import base64

def int_to_bytes(i, length):
    return i.to_bytes(length, byteorder='big')

def generate_vapid_keys():
    # Generate private key
    private_key = ec.generate_private_key(ec.SECP256R1())
    
    # Get private numbers
    private_val = private_key.private_numbers().private_value
    private_bytes = int_to_bytes(private_val, 32)
    private_b64 = base64.urlsafe_b64encode(private_bytes).decode('utf-8').rstrip('=')
    
    # Get public key
    public_key = private_key.public_key()
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )
    public_b64 = base64.urlsafe_b64encode(public_bytes).decode('utf-8').rstrip('=')
    
    # Read existing .env
    env_content = ""
    if os.path.exists('.env'):
        with open('.env', 'r') as f:
            env_content = f.read()
    
    # Append if not present
    with open('.env', 'a') as f:
        if 'VAPID_PRIVATE_KEY' not in env_content:
            f.write(f"\n\n# VAPID Keys for Push Notifications\n")
            f.write(f"VAPID_PRIVATE_KEY={private_b64}\n")
            f.write(f"VAPID_PUBLIC_KEY={public_b64}\n")
            f.write(f"VAPID_CLAIMS_EMAIL=mailto:admin@abhihub.com\n")
            print("Keys appended to .env")
        else:
            print("VAPID keys already present in .env")

if __name__ == "__main__":
    import os
    generate_vapid_keys()
