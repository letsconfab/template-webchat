"""Library copies and root-folder copies of one Drive file stay separate in the index."""

from __future__ import annotations

import unittest

from backend.services.cocoindex_pipeline import qdrant_delete_filter, qdrant_point_id

NAME = "doc_aaaaaaaaaa_Sample Practice.txt"


class IndexKeyTests(unittest.TestCase):
    def test_same_filename_in_library_and_drive_gets_distinct_point_ids(self) -> None:
        self.assertNotEqual(qdrant_point_id(NAME, "library", 0), qdrant_point_id(NAME, "drive", 0))

    def test_point_ids_are_stable_across_processes(self) -> None:
        self.assertEqual(qdrant_point_id(NAME, "drive", 3), qdrant_point_id(NAME, "drive", 3))
        self.assertLess(qdrant_point_id(NAME, "drive", 3), 2**63)

    def test_reindexing_a_drive_copy_never_deletes_library_chunks(self) -> None:
        self.assertEqual(
            qdrant_delete_filter(NAME, "drive"),
            {
                "must": [{"key": "filename", "match": {"value": NAME}}],
                "must_not": [{"key": "source_dir", "match": {"value": "library"}}],
            },
        )

    def test_reindexing_a_library_copy_deletes_only_library_chunks(self) -> None:
        self.assertEqual(
            qdrant_delete_filter(NAME, "library"),
            {
                "must": [
                    {"key": "filename", "match": {"value": NAME}},
                    {"key": "source_dir", "match": {"value": "library"}},
                ]
            },
        )


if __name__ == "__main__":
    unittest.main()
