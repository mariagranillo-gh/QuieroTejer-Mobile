import hashlib
import secrets

def hash_password(password: str) -> str:
    """
    Hashea una contraseña usando PBKDF2-HMAC-SHA256 con un salt aleatorio.
    Retorna un string con formato 'pbkdf2_sha256$iterations$salt$hash'.
    """
    if not password:
        return ""
    salt = secrets.token_hex(16)
    iterations = 100000
    dk = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        iterations
    )
    password_hash = dk.hex()
    return f"pbkdf2_sha256${iterations}${salt}${password_hash}"

def verify_password(password: str, encoded_hash: str) -> bool:
    """
    Verifica una contraseña contra un hash almacenado con formato 'pbkdf2_sha256$iterations$salt$hash'.
    """
    if not password or not encoded_hash:
        return False
    try:
        parts = encoded_hash.split('$')
        if len(parts) != 4:
            return False
        algorithm, iterations_str, salt, stored_hash = parts
        if algorithm != 'pbkdf2_sha256':
            return False
        iterations = int(iterations_str)
        dk = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            iterations
        )
        return dk.hex() == stored_hash
    except Exception:
        return False
