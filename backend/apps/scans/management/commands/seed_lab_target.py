"""Seed the Compose lab-target into demo inventory (idempotent)."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from apps.scans.models import AllowlistEntry, Target, TargetGroup

LAB_DOMAIN = "lab-target.surfacex.local"
LAB_IP = "172.30.0.10"
LAB_GROUP = "lab-local"
LAB_COMMENT = "Compose lab-target (HTTP/TLS demo fixture)"


class Command(BaseCommand):
    help = (
        "Ensure demo users have lab-target host + lab-local group ready to scan "
        "(domain lab-target.surfacex.local and IP 172.30.0.10)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default="admin",
            help="Primary owner username (default: admin). Also seeds operator if present.",
        )

    def handle(self, *args, **options):
        usernames = [options["username"]]
        if "operator" not in usernames and User.objects.filter(username="operator").exists():
            usernames.append("operator")

        seeded = 0
        for username in usernames:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(
                        f"User '{username}' missing — skip "
                        "(run bootstrap_admin first)."
                    )
                )
                continue
            self._seed_user(user)
            seeded += 1

        if seeded:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Lab demo inventory ready for {seeded} user(s): "
                    f"{LAB_DOMAIN} + {LAB_IP} → group {LAB_GROUP}"
                )
            )

    def _seed_user(self, user: User) -> None:
        domain_target, _ = Target.objects.get_or_create(
            owner=user,
            address=LAB_DOMAIN,
            defaults={
                "target_type": Target.Type.DOMAIN,
                "comment": LAB_COMMENT,
            },
        )
        if domain_target.comment != LAB_COMMENT:
            domain_target.comment = LAB_COMMENT
            domain_target.save(update_fields=["comment", "updated_at"])

        ip_target, _ = Target.objects.get_or_create(
            owner=user,
            address=LAB_IP,
            defaults={
                "target_type": Target.Type.IP,
                "comment": LAB_COMMENT,
            },
        )
        if ip_target.comment != LAB_COMMENT:
            ip_target.comment = LAB_COMMENT
            ip_target.save(update_fields=["comment", "updated_at"])

        for value, entry_type in (
            (LAB_DOMAIN, AllowlistEntry.EntryType.DOMAIN),
            (LAB_IP, AllowlistEntry.EntryType.IP),
        ):
            entry, _ = AllowlistEntry.objects.get_or_create(
                owner=user,
                value=value,
                defaults={
                    "entry_type": entry_type,
                    "enabled": True,
                    "comment": LAB_COMMENT,
                },
            )
            if not entry.enabled:
                entry.enabled = True
                entry.save(update_fields=["enabled", "updated_at"])

        group, _ = TargetGroup.objects.get_or_create(
            owner=user,
            name=LAB_GROUP,
            defaults={
                "description": "Local Compose lab-target container (HTTP/TLS)",
            },
        )
        group.targets.add(domain_target, ip_target)
