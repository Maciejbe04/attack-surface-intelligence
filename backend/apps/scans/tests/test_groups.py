from __future__ import annotations

from datetime import datetime, time, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import UserProfile
from apps.scans.groups import compute_next_run, dispatch_due_schedules
from apps.scans.import_targets import parse_import_payload
from apps.scans.models import GroupSchedule, ScanRun, Target, TargetGroup

PUBLISH = "apps.scans.services.execute_batch.apply_async"
MODULES = [{"id": "port-scan", "filters": {}}]


def create_user(username: str, role: str) -> User:
    user = User.objects.create_user(username=username, password="test-password")
    UserProfile.objects.create(user=user, role=role)
    return user


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=dt_timezone.utc)


class GroupTestCase(TestCase):
    def setUp(self) -> None:
        self.operator = create_user("operator", UserProfile.Role.OPERATOR)
        self.other = create_user("other", UserProfile.Role.OPERATOR)
        self.viewer = create_user("viewer", UserProfile.Role.VIEWER)
        self.client = APIClient()
        self.client.force_login(self.operator)

    def target(self, address: str, owner: User | None = None, comment: str = "") -> Target:
        return Target.objects.create(
            owner=owner or self.operator,
            address=address,
            target_type=Target.Type.DOMAIN if "." in address and not address[0].isdigit() else Target.Type.IP,
            comment=comment,
        )

    def group(self, name: str, *targets: Target, owner: User | None = None) -> TargetGroup:
        group = TargetGroup.objects.create(owner=owner or self.operator, name=name)
        group.targets.add(*targets)
        return group


class GroupAPITests(GroupTestCase):
    def test_create_list_and_case_insensitive_unique_name(self) -> None:
        response = self.client.post(reverse("group-list"), {"name": "  DMZ   web "}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["name"], "DMZ web")
        self.assertEqual(response.json()["target_count"], 0)
        self.assertIsNone(response.json()["schedule"])

        response = self.client.post(reverse("group-list"), {"name": "dmz WEB"}, format="json")
        self.assertEqual(response.status_code, 400)

        # Another owner may use the same name.
        self.client.force_login(self.other)
        response = self.client.post(reverse("group-list"), {"name": "DMZ web"}, format="json")
        self.assertEqual(response.status_code, 201)

    def test_groups_are_owner_scoped_and_viewer_is_read_only(self) -> None:
        self.group("theirs", owner=self.other)
        mine = self.group("mine")
        response = self.client.get(reverse("group-list"))
        self.assertEqual([item["id"] for item in response.json()], [mine.id])
        other_group = TargetGroup.objects.get(name="theirs")
        self.assertEqual(
            self.client.get(reverse("group-detail", args=[other_group.id])).status_code,
            404,
        )

        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse("group-list")).status_code, 200)
        response = self.client.post(reverse("group-list"), {"name": "x"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_add_and_remove_members(self) -> None:
        first, second = self.target("192.0.2.1"), self.target("192.0.2.2")
        group = self.group("lab")
        url = reverse("group-targets", args=[group.id])

        response = self.client.post(
            url, {"action": "add", "target_ids": [first.id, second.id]}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["target_count"], 2)
        self.assertEqual(response.json()["changed_count"], 2)

        response = self.client.post(
            url, {"action": "add", "target_ids": [first.id]}, format="json"
        )
        self.assertEqual(response.json()["changed_count"], 0)

        response = self.client.post(
            url, {"action": "remove", "target_ids": [first.id]}, format="json"
        )
        self.assertEqual(response.json()["target_count"], 1)
        self.assertTrue(Target.objects.filter(pk=first.pk).exists())

    def test_members_must_belong_to_group_owner(self) -> None:
        foreign = self.target("192.0.2.9", owner=self.other)
        group = self.group("lab")
        response = self.client.post(
            reverse("group-targets", args=[group.id]),
            {"action": "add", "target_ids": [foreign.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(group.targets.count(), 0)

    def test_deleting_group_keeps_targets(self) -> None:
        member = self.target("192.0.2.3")
        group = self.group("temp", member)
        response = self.client.delete(reverse("group-detail", args=[group.id]))
        self.assertEqual(response.status_code, 204)
        self.assertTrue(Target.objects.filter(pk=member.pk).exists())

    def test_rename_group(self) -> None:
        group = self.group("old-name")
        response = self.client.patch(
            reverse("group-detail", args=[group.id]),
            {"name": "new-name", "description": "renamed"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "new-name")
        self.assertEqual(response.json()["description"], "renamed")
        group.refresh_from_db()
        self.assertEqual(group.name, "new-name")


class TargetSearchTests(GroupTestCase):
    def test_search_group_filter_limit_and_ranking(self) -> None:
        exact = self.target("web.example.test")
        prefix = self.target("web.example.test.internal.example.test")
        middle = self.target("old-web.example.test", comment="legacy")
        self.target("db.example.test", comment="primary web database")
        self.target("192.0.2.40", owner=self.other)
        lab = self.group("lab", exact, middle)

        response = self.client.get(reverse("target-list"), {"search": "web.example.test", "limit": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()],
            [exact.id, prefix.id],
        )

        # Comments are searched too; other owners' targets never leak.
        response = self.client.get(reverse("target-list"), {"search": "WEB"})
        self.assertEqual(len(response.json()), 4)

        response = self.client.get(reverse("target-list"), {"group": lab.id})
        self.assertEqual({item["id"] for item in response.json()}, {exact.id, middle.id})
        self.assertEqual(response.json()[0]["groups"], [{"id": lab.id, "name": "lab"}])

        self.assertEqual(
            self.client.get(reverse("target-list"), {"limit": 0}).status_code,
            400,
        )


class GroupScanTests(GroupTestCase):
    def test_scan_whole_group(self) -> None:
        group = self.group("lab", self.target("192.0.2.1"), self.target("192.0.2.2"))
        with patch(PUBLISH) as publish, self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("group-scan", args=[group.id]),
                {"modules": MODULES, "client_request_id": "group-scan-1"},
                format="json",
            )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["group_id"], group.id)
        self.assertEqual(body["group_name"], "lab")
        self.assertFalse(body["scheduled"])
        self.assertEqual(body["total_batches"], 2)
        self.assertEqual(publish.call_count, 2)

        listed = self.client.get(reverse("scan-list")).json()[0]
        self.assertEqual(listed["group_name"], "lab")

    def test_operator_group_scan_uses_request_context_for_window_limit(self) -> None:
        group = self.group("lab", self.target("192.0.2.1"))
        url = reverse("group-scan", args=[group.id])

        with patch(PUBLISH), self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                url,
                {
                    "modules": MODULES,
                    "client_request_id": "group-window-1h",
                    "window_seconds": 3600,
                },
                format="json",
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["window_seconds"], 3600)

        response = self.client.post(
            url,
            {
                "modules": MODULES,
                "client_request_id": "group-window-2h",
                "window_seconds": 7200,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("window_seconds", response.json())

    def test_empty_group_cannot_be_scanned(self) -> None:
        group = self.group("empty")
        response = self.client.post(
            reverse("group-scan", args=[group.id]), {"modules": MODULES}, format="json"
        )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(ScanRun.objects.exists())


class GroupImportTests(GroupTestCase):
    def post_file(self, name: str, content: bytes, **fields):
        upload = SimpleUploadedFile(name, content, content_type="text/plain")
        return self.client.post(
            reverse("target-import"),
            {"file": upload, "start_scan": "false", **fields},
            format="multipart",
        )

    def test_txt_import_into_new_group(self) -> None:
        existing = self.target("192.0.2.1")
        response = self.post_file("hosts.txt", b"192.0.2.1\n192.0.2.2\n", group_name="Branch office")
        self.assertEqual(response.status_code, 201)
        group = TargetGroup.objects.get(owner=self.operator, name="Branch office")
        self.assertEqual(
            set(group.targets.values_list("address", flat=True)),
            {"192.0.2.1", "192.0.2.2"},
        )
        self.assertIn(existing, group.targets.all())
        self.assertEqual(
            response.json()["groups"],
            [{"id": group.id, "name": "Branch office", "created": True, "added_count": 2}],
        )
        self.assertEqual(response.json()["targets"][0]["groups"][0]["name"], "Branch office")

    def test_txt_import_into_existing_group_and_name_reuse(self) -> None:
        group = self.group("Lab")
        response = self.post_file("hosts.txt", b"192.0.2.5\n", group_id=str(group.id))
        self.assertEqual(response.status_code, 201)
        self.post_file("hosts.txt", b"192.0.2.6\n", group_name="lab")
        self.assertEqual(TargetGroup.objects.filter(owner=self.operator).count(), 1)
        self.assertEqual(group.targets.count(), 2)

    def test_csv_group_column_assigns_per_row_groups(self) -> None:
        response = self.post_file(
            "hosts.csv",
            (
                b"address,group,comment\n"
                b"192.0.2.10,DMZ;Web,front\n"
                b"192.0.2.11,DMZ,\n"
                b"192.0.2.12,,no group\n"
            ),
            group_name="Imported",
        )
        self.assertEqual(response.status_code, 201)
        members = {
            group.name: set(group.targets.values_list("address", flat=True))
            for group in TargetGroup.objects.filter(owner=self.operator)
        }
        self.assertEqual(members["DMZ"], {"192.0.2.10", "192.0.2.11"})
        self.assertEqual(members["Web"], {"192.0.2.10"})
        self.assertEqual(members["Imported"], {"192.0.2.10", "192.0.2.11", "192.0.2.12"})

    def test_group_of_another_user_is_rejected(self) -> None:
        foreign = self.group("theirs", owner=self.other)
        response = self.post_file("hosts.txt", b"192.0.2.7\n", group_id=str(foreign.id))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Target.objects.filter(address="192.0.2.7").exists())

    def test_import_and_scan_records_group_on_run(self) -> None:
        with patch(PUBLISH), self.captureOnCommitCallbacks(execute=True):
            response = self.post_file(
                "hosts.txt",
                b"192.0.2.20\n",
                group_name="Night",
                start_scan="true",
                modules='[{"id": "port-scan", "filters": {}}]',
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["scan"]["group_name"], "Night")

    def test_parser_merges_groups_of_duplicate_rows(self) -> None:
        parsed = parse_import_payload(
            filename="hosts.csv",
            raw=b"host,groups\n192.0.2.1,A\n192.0.2.1,B|a\n",
        )
        self.assertEqual(len(parsed.targets), 1)
        self.assertEqual(parsed.targets[0].groups, ("A", "B"))


class NextRunTests(TestCase):
    def schedule(self, **kwargs) -> GroupSchedule:
        defaults = {"frequency": "daily", "time_of_day": time(2, 0), "weekday": 0, "interval_hours": 6}
        defaults.update(kwargs)
        return GroupSchedule(**defaults)

    def test_daily(self) -> None:
        schedule = self.schedule(frequency="daily", time_of_day=time(2, 0))
        self.assertEqual(compute_next_run(schedule, utc(2026, 11, 21, 1, 30)), utc(2026, 11, 21, 2, 0))
        self.assertEqual(compute_next_run(schedule, utc(2026, 11, 21, 2, 0)), utc(2026, 11, 22, 2, 0))

    def test_weekly(self) -> None:
        # 2026-11-21 is a Saturday; weekday 0 = Monday.
        schedule = self.schedule(frequency="weekly", weekday=0, time_of_day=time(6, 30))
        self.assertEqual(compute_next_run(schedule, utc(2026, 11, 21, 12, 0)), utc(2026, 11, 23, 6, 30))
        self.assertEqual(compute_next_run(schedule, utc(2026, 11, 23, 6, 30)), utc(2026, 11, 30, 6, 30))

    def test_hourly(self) -> None:
        schedule = self.schedule(frequency="hourly", interval_hours=6)
        self.assertEqual(compute_next_run(schedule, utc(2026, 11, 21, 10, 15, 42)), utc(2026, 11, 21, 16, 15))


class ScheduleAPITests(GroupTestCase):
    def test_put_schedule_plans_next_run_and_delete_removes_it(self) -> None:
        group = self.group("lab")
        url = reverse("group-schedule", args=[group.id])
        response = self.client.put(
            url,
            {"frequency": "daily", "time_of_day": "03:15", "modules": MODULES},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        schedule = response.json()["schedule"]
        self.assertTrue(schedule["enabled"])
        self.assertEqual(schedule["time_of_day"], "03:15")
        self.assertEqual(schedule["modules"][0]["filters"]["profile"], "discovery-fast")
        self.assertIsNotNone(schedule["next_run_at"])

        response = self.client.put(
            url,
            {"enabled": False, "frequency": "daily", "time_of_day": "03:15", "modules": MODULES},
            format="json",
        )
        self.assertIsNone(response.json()["schedule"]["next_run_at"])

        self.assertIsNone(self.client.delete(url).json()["schedule"])

    def test_schedule_validation(self) -> None:
        group = self.group("lab")
        url = reverse("group-schedule", args=[group.id])
        for payload in (
            {"frequency": "weekly", "weekday": 7, "time_of_day": "03:00", "modules": MODULES},
            {"frequency": "hourly", "interval_hours": 0, "time_of_day": "03:00", "modules": MODULES},
            {"frequency": "monthly", "time_of_day": "03:00", "modules": MODULES},
            {"frequency": "daily", "time_of_day": "25:00", "modules": MODULES},
            {"frequency": "daily", "time_of_day": "03:00", "modules": [{"id": "rm -rf", "filters": {}}]},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.put(url, payload, format="json").status_code, 400)

        self.client.force_login(self.viewer)
        response = self.client.put(
            url, {"frequency": "daily", "time_of_day": "03:00", "modules": MODULES}, format="json"
        )
        self.assertEqual(response.status_code, 403)


class DispatchTests(GroupTestCase):
    def make_schedule(self, group: TargetGroup, **kwargs) -> GroupSchedule:
        defaults = {
            "frequency": GroupSchedule.Frequency.DAILY,
            "time_of_day": time(2, 0),
            "modules_snapshot": MODULES,
            "next_run_at": utc(2026, 11, 21, 2, 0),
        }
        defaults.update(kwargs)
        return GroupSchedule.objects.create(group=group, **defaults)

    def dispatch(self, now: datetime) -> dict:
        with patch(PUBLISH) as publish, self.captureOnCommitCallbacks(execute=True):
            result = dispatch_due_schedules(now)
        self.publish_calls = publish.call_count
        return result

    def test_due_schedule_queues_group_scan_and_replans(self) -> None:
        group = self.group("lab", self.target("192.0.2.1"), self.target("192.0.2.2"))
        schedule = self.make_schedule(group)

        result = self.dispatch(utc(2026, 11, 21, 2, 0, 30))
        self.assertEqual(result, {"due": 1, "dispatched": 1, "skipped": 0})
        self.assertEqual(self.publish_calls, 2)

        run = ScanRun.objects.get()
        self.assertEqual((run.owner, run.group, run.schedule), (self.operator, group, schedule))
        schedule.refresh_from_db()
        self.assertEqual(schedule.last_run, run)
        self.assertEqual(schedule.next_run_at, utc(2026, 11, 22, 2, 0))
        self.assertIn(f"#{run.pk}", schedule.last_status)

        # Not due again until tomorrow.
        self.assertEqual(self.dispatch(utc(2026, 11, 21, 2, 5))["due"], 0)

    def test_skips_while_previous_run_is_active(self) -> None:
        group = self.group("lab", self.target("192.0.2.1"))
        active = ScanRun.objects.create(owner=self.operator, status=ScanRun.Status.RUNNING)
        schedule = self.make_schedule(group, last_run=active)

        result = self.dispatch(utc(2026, 11, 21, 2, 1))
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(ScanRun.objects.count(), 1)
        schedule.refresh_from_db()
        self.assertIn("still active", schedule.last_status)
        self.assertEqual(schedule.next_run_at, utc(2026, 11, 22, 2, 0))

    def test_disabled_and_empty_groups(self) -> None:
        self.make_schedule(self.group("off", self.target("192.0.2.1")), enabled=False)
        empty = self.make_schedule(self.group("empty"))
        result = self.dispatch(utc(2026, 11, 21, 3, 0))
        self.assertEqual(result, {"due": 1, "dispatched": 0, "skipped": 1})
        empty.refresh_from_db()
        self.assertIn("no targets", empty.last_status)
        self.assertFalse(ScanRun.objects.exists())

    def test_missed_occurrences_run_once(self) -> None:
        group = self.group("lab", self.target("192.0.2.1"))
        schedule = self.make_schedule(group, next_run_at=utc(2026, 11, 18, 2, 0))
        self.dispatch(utc(2026, 11, 21, 9, 0))
        self.assertEqual(ScanRun.objects.count(), 1)
        schedule.refresh_from_db()
        self.assertEqual(schedule.next_run_at, utc(2026, 11, 22, 2, 0))


@override_settings(WORKER_TOKEN="worker-test-token")
class ScheduleDispatchEndpointTests(GroupTestCase):
    def test_requires_worker_token(self) -> None:
        client = APIClient()
        url = reverse("internal-schedule-dispatch")
        self.assertEqual(client.post(url, {}, format="json").status_code, 403)
        with patch(PUBLISH):
            response = client.post(
                url, {}, format="json", HTTP_X_WORKER_TOKEN="worker-test-token"
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"due": 0, "dispatched": 0, "skipped": 0})

    def test_beat_runs_dispatch_every_minute(self) -> None:
        from django.conf import settings

        entry = settings.CELERY_BEAT_SCHEDULE["dispatch-group-schedules"]
        self.assertEqual(entry["task"], "scans.dispatch_schedules")
        self.assertEqual(timedelta(seconds=entry["schedule"]), timedelta(minutes=1))
