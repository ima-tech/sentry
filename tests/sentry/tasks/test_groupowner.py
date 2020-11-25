from __future__ import absolute_import

from django.utils import timezone

from sentry.eventstore.processing import event_processing_store
from sentry.tasks.groupowner import process_suspect_commits, PREFERRED_GROUP_OWNER_AGE
from sentry.testutils import TestCase
from sentry.testutils.helpers.datetime import iso_format, before_now
from sentry.models import Repository, GroupOwner
from sentry.utils.committers import get_serialized_event_file_committers


class TestGroupOwners(TestCase):
    def setUp(self):
        self.project = self.create_project()
        self.repo = Repository.objects.create(
            organization_id=self.organization.id, name=self.organization.id
        )
        self.release = self.create_release(project=self.project, version="v1337")
        self.group = self.create_group(
            project=self.project, message="Kaboom!", first_release=self.release
        )

        self.event_1 = self.store_event(
            data={
                "message": "Kaboom!",
                "platform": "python",
                "timestamp": iso_format(before_now(seconds=10)),
                "stacktrace": {
                    "frames": [
                        {
                            "function": "handle_set_commits",
                            "abs_path": "/usr/src/sentry/src/sentry/tasks.py",
                            "module": "sentry.tasks",
                            "in_app": True,
                            "lineno": 30,
                            "filename": "sentry/tasks.py",
                        },
                        {
                            "function": "set_commits",
                            "abs_path": "/usr/src/sentry/src/sentry/models/release.py",
                            "module": "sentry.models.release",
                            "in_app": True,
                            "lineno": 39,
                            "filename": "sentry/models/release.py",
                        },
                    ]
                },
                "tags": {"sentry:release": self.release.version},
                "fingerprint": ["put-me-in-the-control-group"],
            },
            project_id=self.project.id,
        )

    def set_release_commits(self, author_email):
        self.release.set_commits(
            [
                {
                    "id": "a" * 40,
                    "repository": self.repo.name,
                    "author_email": author_email,
                    "author_name": "Bob",
                    "message": "i fixed a bug",
                    "patch_set": [{"path": "src/sentry/models/release.py", "type": "M"}],
                }
            ]
        )

    def test_simple(self):
        self.set_release_commits(self.user.email)

        result = get_serialized_event_file_committers(self.project, self.event_1)

        assert len(result) == 1
        assert "commits" in result[0]
        assert len(result[0]["commits"]) == 1
        assert result[0]["commits"][0]["id"] == "a" * 40

        data = self.event_1.data
        data["event_id"] = self.event_1.event_id
        data["project"] = self.event_1.project_id
        cache_key = event_processing_store.store(data)

        assert not GroupOwner.objects.filter(group=self.event_1.group).exists()
        process_suspect_commits(self.event_1.group_id, cache_key)
        assert GroupOwner.objects.filter(group=self.event_1.group).exists()

    def test_no_matching_user(self):
        self.set_release_commits("not@real.user")

        result = get_serialized_event_file_committers(self.project, self.event_1)

        assert len(result) == 1
        assert "commits" in result[0]
        assert len(result[0]["commits"]) == 1
        assert result[0]["commits"][0]["id"] == "a" * 40

        data = self.event_1.data
        data["event_id"] = self.event_1.event_id
        data["project"] = self.event_1.project_id
        cache_key = event_processing_store.store(data)

        assert not GroupOwner.objects.filter(group=self.event_1.group).exists()
        process_suspect_commits(self.event_1.group_id, cache_key)
        assert not GroupOwner.objects.filter(group=self.event_1.group).exists()

    def test_delete_old_entries(self):
        # As new events come in associated with new owners, we should delete old ones.
        self.set_release_commits(self.user.email)
        gid = self.event_1.group_id
        data = self.event_1.data
        data["event_id"] = self.event_1.event_id
        data["project"] = self.event_1.project_id
        cache_key = event_processing_store.store(data)
        process_suspect_commits(gid, cache_key)
        cache_key = event_processing_store.store(data)
        process_suspect_commits(gid, cache_key)
        cache_key = event_processing_store.store(data)
        process_suspect_commits(gid, cache_key)

        assert GroupOwner.objects.filter(group=self.event_1.group).count() == 1
        assert GroupOwner.objects.filter(group=self.event_1.group, user=self.user).exists()
        self.event_2 = self.store_event(
            data={
                "message": "BANG!",
                "platform": "python",
                "timestamp": iso_format(before_now(seconds=1)),
                "stacktrace": {
                    "frames": [
                        {
                            "function": "process_suspect_commits",
                            "abs_path": "/usr/src/sentry/src/sentry/tasks/groupowner.py",
                            "module": "sentry.tasks.groupowner",
                            "in_app": True,
                            "lineno": 48,
                            "filename": "sentry/tasks/groupowner.py",
                        },
                    ]
                },
                "tags": {"sentry:release": self.release.version},
                "fingerprint": ["put-me-in-the-control-group"],
            },
            project_id=self.project.id,
        )
        self.event_3 = self.store_event(
            data={
                "message": "BOP!",
                "platform": "python",
                "timestamp": iso_format(before_now(seconds=1)),
                "stacktrace": {
                    "frames": [
                        {
                            "function": "process_suspect_commits",
                            "abs_path": "/usr/src/sentry/src/sentry/tasks/groupowner.py",
                            "module": "sentry.tasks.groupowner",
                            "in_app": True,
                            "lineno": 48,
                            "filename": "sentry/tasks/groupowner.py",
                        },
                    ]
                },
                "tags": {"sentry:release": self.release.version},
                "fingerprint": ["put-me-in-the-control-group"],
            },
            project_id=self.project.id,
        )
        self.event_4 = self.store_event(
            data={
                "message": "BAP!",
                "platform": "python",
                "timestamp": iso_format(before_now(seconds=1)),
                "stacktrace": {
                    "frames": [
                        {
                            "function": "process_suspect_commits",
                            "abs_path": "/usr/src/sentry/src/sentry/tasks/groupowner.py",
                            "module": "sentry.tasks.groupowner",
                            "in_app": True,
                            "lineno": 48,
                            "filename": "sentry/tasks/groupowner.py",
                        },
                    ]
                },
                "tags": {"sentry:release": self.release.version},
                "fingerprint": ["put-me-in-the-control-group"],
            },
            project_id=self.project.id,
        )
        self.user_2 = self.create_user("another@user.com", is_superuser=True)
        self.create_member(teams=[self.team], user=self.user_2, organization=self.organization)
        self.user_3 = self.create_user("user_3@sentry.io", is_superuser=True)
        self.create_member(teams=[self.team], user=self.user_3, organization=self.organization)
        self.user_4 = self.create_user("user_4@sentry.io", is_superuser=True)
        self.create_member(teams=[self.team], user=self.user_4, organization=self.organization)
        self.release.set_commits(
            [
                {
                    "id": "a" * 40,
                    "repository": self.repo.name,
                    "author_email": self.user_2.email,
                    "author_name": "joe",
                    "message": "i fixed another bug",
                    "patch_set": [{"path": "src/sentry/tasks/groupowner.py", "type": "M"}],
                }
            ]
        )

        assert self.event_2.group == self.event_1.group
        assert self.event_3.group == self.event_1.group
        assert self.event_4.group == self.event_1.group

        data = self.event_2.data
        data["event_id"] = self.event_2.event_id
        data["project"] = self.event_2.project_id
        cache_key = event_processing_store.store(data)

        self.set_release_commits(self.user_2.email)
        process_suspect_commits(self.event_2.group_id, cache_key)
        assert GroupOwner.objects.filter(group=self.event_1.group).count() == 2
        assert GroupOwner.objects.filter(group=self.event_1.group, user=self.user).exists()
        assert GroupOwner.objects.filter(group=self.event_2.group, user=self.user_2).exists()

        data = self.event_3.data
        data["event_id"] = self.event_3.event_id
        data["project"] = self.event_3.project_id
        cache_key = event_processing_store.store(data)
        self.set_release_commits(self.user_3.email)
        process_suspect_commits(self.event_3.group_id, cache_key)
        assert GroupOwner.objects.filter(group=self.event_1.group).count() == 3
        assert GroupOwner.objects.filter(group=self.event_1.group, user=self.user).exists()
        assert GroupOwner.objects.filter(group=self.event_2.group, user=self.user_2).exists()
        assert GroupOwner.objects.filter(group=self.event_2.group, user=self.user_3).exists()

        data = self.event_4.data
        data["event_id"] = self.event_4.event_id
        data["project"] = self.event_4.project_id
        cache_key = event_processing_store.store(data)
        self.set_release_commits(self.user_4.email)
        process_suspect_commits(self.event_4.group_id, cache_key)
        assert GroupOwner.objects.filter(group=self.event_1.group).count() == 3
        assert GroupOwner.objects.filter(group=self.event_1.group, user=self.user).exists()
        assert GroupOwner.objects.filter(group=self.event_2.group, user=self.user_2).exists()
        assert GroupOwner.objects.filter(group=self.event_2.group, user=self.user_3).exists()
        assert not GroupOwner.objects.filter(group=self.event_2.group, user=self.user_4).exists()

        go = GroupOwner.objects.filter(group=self.event_2.group, user=self.user_2).first()
        go.date_added = timezone.now() - PREFERRED_GROUP_OWNER_AGE * 2
        go.save()

        data = self.event_4.data
        data["event_id"] = self.event_4.event_id
        data["project"] = self.event_4.project_id
        cache_key = event_processing_store.store(data)
        self.set_release_commits(self.user_4.email)
        process_suspect_commits(self.event_4.group_id, cache_key)
        assert GroupOwner.objects.filter(group=self.event_1.group).count() == 3
        assert GroupOwner.objects.filter(group=self.event_1.group, user=self.user).exists()
        assert not GroupOwner.objects.filter(group=self.event_2.group, user=self.user_2).exists()
        assert GroupOwner.objects.filter(group=self.event_2.group, user=self.user_3).exists()
        assert GroupOwner.objects.filter(group=self.event_2.group, user=self.user_4).exists()

    def test_update_existing_entries(self):
        # As new events come in associated with existing owners, we should update the date_added of that owner.
        pass