import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.cli.create_admin import reset_admin_password
from app.db.base import Base
from app.models import User, UserRole
from app.services.security import hash_password, verify_password


class AdminPasswordResetTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        User.__table__.create(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def add_user(self, email, role):
        user = User(
            name="Test account",
            email=email,
            password_hash=hash_password("old-password-123"),
            role=role,
        )
        self.session.add(user)
        self.session.commit()
        return user

    def test_successful_reset_updates_existing_admin_hash(self):
        user = self.add_user("admin@example.com", UserRole.ADMIN)

        reset_admin_password(self.session, user.email, "new-password-456")

        self.assertNotEqual(user.password_hash, "new-password-456")
        self.assertTrue(verify_password("new-password-456", user.password_hash))
        self.assertFalse(verify_password("old-password-123", user.password_hash))
        self.assertEqual(self.session.query(User).count(), 1)

    def test_nonexistent_email_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "no account"):
            reset_admin_password(self.session, "missing@example.com", "new-password-456")

    def test_non_admin_account_is_rejected_without_role_change(self):
        user = self.add_user("patient@example.com", UserRole.PATIENT)
        old_hash = user.password_hash

        with self.assertRaisesRegex(ValueError, "not an administrator"):
            reset_admin_password(self.session, user.email, "new-password-456")

        self.session.refresh(user)
        self.assertEqual(user.role, UserRole.PATIENT)
        self.assertEqual(user.password_hash, old_hash)

    def test_password_verification_uses_project_hashing_method(self):
        user = self.add_user("admin@example.com", UserRole.ADMIN)

        reset_admin_password(self.session, user.email, "new-password-456")

        self.assertTrue(verify_password("new-password-456", user.password_hash))


if __name__ == "__main__":
    unittest.main()
