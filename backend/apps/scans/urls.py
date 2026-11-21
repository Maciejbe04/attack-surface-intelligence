from django.urls import path

from . import internal_views, views

urlpatterns = [
    path("targets/", views.TargetListCreateView.as_view(), name="target-list"),
    path(
        "targets/<int:target_id>/",
        views.TargetDetailView.as_view(),
        name="target-detail",
    ),
    path("scans/", views.ScanListCreateView.as_view(), name="scan-list"),
    path(
        "scans/<int:run_id>/",
        views.ScanDetailView.as_view(),
        name="scan-detail",
    ),
    path(
        "scans/<int:run_id>/cancel/",
        views.ScanCancelView.as_view(),
        name="scan-cancel",
    ),
    path(
        "internal/batches/<int:batch_id>/claim/",
        internal_views.BatchClaimView.as_view(),
        name="internal-batch-claim",
    ),
    path(
        "internal/batches/<int:batch_id>/progress/",
        internal_views.BatchProgressView.as_view(),
        name="internal-batch-progress",
    ),
    path(
        "internal/batches/<int:batch_id>/cancel-check/",
        internal_views.BatchCancelCheckView.as_view(),
        name="internal-batch-cancel",
    ),
    path(
        "internal/batches/<int:batch_id>/complete/",
        internal_views.BatchCompleteView.as_view(),
        name="internal-batch-complete",
    ),
    path(
        "internal/batches/<int:batch_id>/fail/",
        internal_views.BatchFailView.as_view(),
        name="internal-batch-fail",
    ),
]
