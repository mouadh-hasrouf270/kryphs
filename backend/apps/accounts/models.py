import uuid

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True)
        return self.create_user(email, password, **extra)


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=150, blank=True)
    last_seen_at = models.DateTimeField(null=True)
    must_change_password = models.BooleanField(default=False)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    def __str__(self):
        return self.display_name or self.email


class UserProfile(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, primary_key=True, related_name="profile"
    )
    avatar = models.URLField(blank=True)
    job_title = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    preferred_language = models.CharField(
        max_length=2, choices=[("ar", "Arabic"), ("en", "English"), ("fr", "French")], default="ar"
    )
    timezone = models.CharField(max_length=80, default="Africa/Algiers")
    locale = models.CharField(max_length=30, default="ar")
    notification_preferences = models.JSONField(default=dict)
    theme = models.CharField(max_length=20, default="light")
