import enum


class ChallengeKind(str, enum.Enum):
    SIGN_UP = "sign_up"
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"
