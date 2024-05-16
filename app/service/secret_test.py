import unittest
from app.service.secret import hash_password, check_password

class Test_Secret(unittest.TestCase):

    def test_hash_password(self):
        password = "mysecretpassword"
        hashed_password = hash_password(password)
        self.assertTrue(isinstance(hashed_password, str), "Hashed password should be a string")
        self.assertNotEqual(password, hashed_password, "Hashed password should not be the same as the plain password")

    def test_check_password(self):
        password = "mysecretpassword"
        hashed_password = hash_password(password)
        self.assertTrue(check_password(password, hashed_password), "check_password should return True for the correct password")
        self.assertFalse(check_password("wrongpassword", hashed_password), "check_password should return False for an incorrect password")

    def test_hash_uniqueness(self):
        password = "mysecretpassword"
        hashed_password1 = hash_password(password)
        hashed_password2 = hash_password(password)
        self.assertNotEqual(hashed_password1, hashed_password2, "Each hash of the same password should be unique")

    def test_check_password_with_different_hash(self):
        password = "mysecretpassword"
        other_password = "anotherpassword"
        hashed_other_password = hash_password(other_password)
        self.assertFalse(check_password(password, hashed_other_password), "check_password should return False when the hash is for a different password")

if __name__ == '__main__':
    unittest.main()
