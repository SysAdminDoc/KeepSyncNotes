import tempfile
import unittest
from pathlib import Path

import keepsync_cloud_plan as cloud_plan
import keepsync_notes as app


class CloudSyncPlanTests(unittest.TestCase):
    def make_note(self, note_id, title="Title", content="Body", labels=None):
        return app.Note(
            id=note_id,
            title=title,
            content=content,
            labels=labels or [],
        )

    def test_plan_upload_and_download_creates(self):
        local = self.make_note("local-only")
        remote = self.make_note("remote-only")

        plan = cloud_plan.build_cloud_sync_plan([local], {"remote-only": remote.to_dict()}, {})

        self.assertEqual([note.id for note in plan["upload_creates"]], ["local-only"])
        self.assertEqual([note["id"] for note in plan["download_creates"]], ["remote-only"])
        self.assertEqual(cloud_plan.cloud_plan_counts(plan), {
            "create": 2,
            "update": 0,
            "delete": 0,
            "conflict": 0,
        })

    def test_plan_conflicts_when_both_changed_since_base(self):
        base = self.make_note("shared", content="Base")
        local = self.make_note("shared", content="Local")
        remote = self.make_note("shared", content="Remote")

        plan = cloud_plan.build_cloud_sync_plan(
            [local],
            {"shared": remote.to_dict()},
            cloud_plan.cloud_base_versions([base]),
        )

        self.assertEqual(len(plan["conflicts"]), 1)
        self.assertEqual(plan["conflicts"][0][0].content, "Local")
        self.assertEqual(plan["conflicts"][0][1]["content"], "Remote")
        self.assertEqual(cloud_plan.cloud_plan_counts(plan)["conflict"], 1)

    def test_plan_conflicts_without_base_for_divergent_shared_note(self):
        local = self.make_note("shared", content="Local")
        remote = self.make_note("shared", content="Remote")

        plan = cloud_plan.build_cloud_sync_plan([local], {"shared": remote.to_dict()}, {})

        self.assertEqual(len(plan["conflicts"]), 1)
        self.assertFalse(plan["upload_updates"])
        self.assertFalse(plan["download_updates"])

    def test_plan_downloads_remote_update_when_local_matches_base(self):
        local = self.make_note("shared", content="Base")
        remote = self.make_note("shared", content="Remote")

        plan = cloud_plan.build_cloud_sync_plan(
            [local],
            {"shared": remote.to_dict()},
            cloud_plan.cloud_base_versions([local]),
        )

        self.assertEqual([note["content"] for note in plan["download_updates"]], ["Remote"])
        self.assertFalse(plan["upload_updates"])
        self.assertFalse(plan["conflicts"])

    def test_plan_deletes_local_when_remote_deleted_and_local_unchanged(self):
        local = self.make_note("shared", content="Base")

        plan = cloud_plan.build_cloud_sync_plan(
            [local],
            {},
            cloud_plan.cloud_base_versions([local]),
        )

        self.assertEqual([note.id for note in plan["delete_local"]], ["shared"])
        self.assertEqual(cloud_plan.cloud_plan_counts(plan)["delete"], 1)

    def test_plan_deletes_remote_when_local_deleted_and_remote_unchanged(self):
        base = self.make_note("shared", content="Base")

        plan = cloud_plan.build_cloud_sync_plan(
            [],
            {"shared": base.to_dict()},
            cloud_plan.cloud_base_versions([base]),
        )

        self.assertEqual([note["id"] for note in plan["delete_remote"]], ["shared"])
        self.assertEqual(cloud_plan.cloud_plan_counts(plan)["delete"], 1)

    def test_cloud_conflict_copy_marks_remote_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = app.DatabaseManager(str(Path(tmp) / "notes.db"))
            try:
                remote = self.make_note("remote", title="Remote", content="Remote body", labels=["work"])

                saved_copy = cloud_plan.save_cloud_conflict_copy(db, remote.to_dict(), "GitHub")

                notes = db.get_all_notes(include_archived=True, include_trashed=True)
                self.assertEqual(len(notes), 1)
                copy = notes[0]
                self.assertEqual(saved_copy.id, copy.id)
                self.assertNotEqual(copy.id, "remote")
                self.assertEqual(copy.title, "Remote (GitHub conflict)")
                self.assertEqual(copy.sync_status, app.SyncStatus.CONFLICT)
                self.assertIn("work", copy.labels)
                self.assertIn("cloud-conflict", copy.labels)
                self.assertIn("github-conflict", copy.labels)
            finally:
                db.close()

    def test_app_reexports_cloud_plan_api_for_compatibility(self):
        self.assertIs(app.build_cloud_sync_plan, cloud_plan.build_cloud_sync_plan)
        self.assertIs(app.cloud_base_versions, cloud_plan.cloud_base_versions)
        self.assertIs(app.cloud_plan_counts, cloud_plan.cloud_plan_counts)
        self.assertIs(app.save_cloud_conflict_copy, cloud_plan.save_cloud_conflict_copy)


if __name__ == "__main__":
    unittest.main()
