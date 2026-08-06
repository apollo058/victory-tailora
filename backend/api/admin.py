from django.contrib import admin

from .models import WorkspaceLayout


@admin.register(WorkspaceLayout)
class WorkspaceLayoutAdmin(admin.ModelAdmin):
    list_display = ("name", "updated_at")
    search_fields = ("name",)

