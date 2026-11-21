from django.contrib import admin

from .models import ScanBatch, ScanRun, Target


@admin.register(Target)
class TargetAdmin(admin.ModelAdmin):
    list_display = ("address", "target_type", "owner", "created_at")
    list_filter = ("target_type",)
    search_fields = ("address", "comment", "owner__username")
    readonly_fields = ("created_at", "updated_at")


class ScanBatchInline(admin.TabularInline):
    model = ScanBatch
    extra = 0
    can_delete = False
    readonly_fields = (
        "target",
        "target_address",
        "target_type",
        "delivery_id",
        "status",
        "progress",
        "claimed_at",
        "finished_at",
    )


@admin.register(ScanRun)
class ScanRunAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "owner",
        "status",
        "progress",
        "total_batches",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("owner__username", "client_request_id")
    readonly_fields = (
        "created_at",
        "started_at",
        "finished_at",
        "updated_at",
    )
    inlines = (ScanBatchInline,)


@admin.register(ScanBatch)
class ScanBatchAdmin(admin.ModelAdmin):
    list_display = ("id", "run", "target_address", "status", "progress")
    list_filter = ("status", "target_type")
    search_fields = ("target_address", "delivery_id")
    readonly_fields = (
        "delivery_id",
        "created_at",
        "claimed_at",
        "finished_at",
        "updated_at",
    )
