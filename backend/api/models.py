from django.db import models


class WorkspaceLayout(models.Model):
    name = models.CharField(max_length=120)
    module_ids = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name

