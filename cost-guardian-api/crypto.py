# crypto.py
from cryptography.fernet import Fernet
from config import MASTER_KEY

def encrypt_key(plain: str) -> bytes:
    """Encrypt a plaintext API key using Fernet symmetric encryption.
    
    Args:
        plain: The plaintext API key to encrypt
        
    Returns:
        bytes: The encrypted key as bytes
        
    Raises:
        ValueError: If MASTER_KEY is not configured
        cryptography.fernet.InvalidToken: If MASTER_KEY is invalid
    """
    if not MASTER_KEY:
        raise ValueError("MASTER_KEY not configured")
    
    fernet = Fernet(MASTER_KEY.encode())
    return fernet.encrypt(plain.encode())

def decrypt_key(cipher: bytes) -> str:
    """Decrypt an encrypted API key using Fernet symmetric encryption.
    
    Args:
        cipher: The encrypted key as bytes
        
    Returns:
        str: The decrypted plaintext API key
        
    Raises:
        ValueError: If MASTER_KEY is not configured
        cryptography.fernet.InvalidToken: If MASTER_KEY is invalid or cipher is corrupted
    """
    if not MASTER_KEY:
        raise ValueError("MASTER_KEY not configured")
    
    fernet = Fernet(MASTER_KEY.encode())
    return fernet.decrypt(cipher).decode()