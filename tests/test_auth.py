from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import greew_quote.auth as auth


class AuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_data_dir = auth.DATA_DIR
        self.old_users_file = auth.USERS_FILE
        self.old_master_user = auth.MASTER_USERNAME
        self.old_master_password = auth.MASTER_PASSWORD

        auth.DATA_DIR = Path(self.tmp.name) / "data"
        auth.USERS_FILE = auth.DATA_DIR / "users.json"
        auth.MASTER_USERNAME = "master"
        auth.MASTER_PASSWORD = "Master@123"

    def tearDown(self) -> None:
        auth.DATA_DIR = self.old_data_dir
        auth.USERS_FILE = self.old_users_file
        auth.MASTER_USERNAME = self.old_master_user
        auth.MASTER_PASSWORD = self.old_master_password
        self.tmp.cleanup()

    def test_register_and_authenticate_user(self) -> None:
        ok, _ = auth.register_user(name="Caio Silva", username="caio", password="segura123")
        self.assertTrue(ok)

        user = auth.authenticate(username="caio", password="segura123")
        self.assertIsNotNone(user)
        self.assertFalse(user.is_master)
        self.assertEqual(user.username, "caio")

    def test_duplicate_user_is_rejected(self) -> None:
        ok, _ = auth.register_user(name="Ana", username="ana", password="senha123")
        self.assertTrue(ok)
        ok2, msg2 = auth.register_user(name="Ana2", username="ana", password="senha456")
        self.assertFalse(ok2)
        self.assertIn("ja cadastrado", msg2)

    def test_master_login(self) -> None:
        user = auth.authenticate(username="master", password="Master@123")
        self.assertIsNotNone(user)
        self.assertTrue(user.is_master)


if __name__ == "__main__":
    unittest.main()
