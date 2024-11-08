import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class UserType(object):
    NORMAL_USER = 'Normal'
    ADMIN = 'Admin'


class User(AbstractUser):
    username = models.CharField(max_length=20, unique=True)
    email = models.EmailField(null=True, blank=True)
    create_time = models.DateTimeField(auto_now_add=True, null=True)
    # 用户类型：Normal/Admin
    user_type = models.CharField(max_length=20, default=UserType.NORMAL_USER)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = 'user'
