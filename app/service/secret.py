import bcrypt


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password=password.encode("utf-8"), salt=salt)
    return hashed_password.decode("utf-8")


def check_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        password=password.encode("utf-8"),
        hashed_password=hashed_password.encode("utf-8"),
    )
