import uuid
from django.db import models


class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Future multi-tenancy: nullable now, required later
    # school = models.ForeignKey("core.School", null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        abstract = True
