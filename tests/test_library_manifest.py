"""Library Manifest parsing: CSV rows → Library Document candidates and issues."""

from __future__ import annotations

import unittest

from backend.services.library import (
    SYSTEMS,
    extract_drive_file_id,
    parse_manifest_csv,
)

HEADER = (
    "Include,Title,Organization,Type,File,"
    "Inspire,Nurture,Trust,Embody,Guide,Regulate,Align,Transcend,Engage,Notes"
)


def _row(
    include="TRUE",
    title="Sample Practice",
    org="Example Org",
    doc_type="LSP",
    link="https://docs.google.com/document/d/doc_aaaaaaaaaa/edit",
    ticked=("Trust",),
    notes="",
) -> str:
    names = [name for _, name in SYSTEMS]
    flags = ["TRUE" if name in ticked else "FALSE" for name in names]
    return ",".join([include, title, org, doc_type, link, *flags, notes])


def _csv(*rows: str, header: str = HEADER) -> str:
    return "\n".join([header, *rows]) + "\n"


class ExtractDriveFileIdTests(unittest.TestCase):
    def test_accepts_document_file_and_open_links(self) -> None:
        cases = {
            "https://docs.google.com/document/d/doc_aaaaaaaaaa/edit?usp=sharing": "doc_aaaaaaaaaa",
            "https://drive.google.com/file/d/pdf-bbbbbbbbbb/view": "pdf-bbbbbbbbbb",
            "https://drive.google.com/open?id=opn_cccccccccc": "opn_cccccccccc",
            "https://docs.google.com/document/u/0/d/doc_uuuuuuuuuu/edit": "doc_uuuuuuuuuu",
        }
        for link, expected in cases.items():
            with self.subTest(link=link):
                self.assertEqual(extract_drive_file_id(link), expected)

    def test_rejects_unparseable_links(self) -> None:
        for link in ("", "not a link", "https://example.test/doc/123"):
            with self.subTest(link=link):
                self.assertIsNone(extract_drive_file_id(link))


class ParseManifestTests(unittest.TestCase):
    def test_reads_only_included_rows_and_maps_systems_to_slugs(self) -> None:
        rows, issues = parse_manifest_csv(
            _csv(
                _row(ticked=("Engage", "Trust")),
                _row(
                    include="FALSE",
                    link="https://docs.google.com/document/d/doc_dddddddddd/edit",
                ),
            )
        )

        self.assertEqual(issues, [])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.file_id, "doc_aaaaaaaaaa")
        self.assertEqual(row.title, "Sample Practice")
        self.assertEqual(row.organization, "Example Org")
        self.assertEqual(row.type, "LSP")
        self.assertEqual(row.systems, ["trust", "engage"])
        self.assertEqual(row.row, 2)

    def test_header_case_and_extra_columns_are_tolerated(self) -> None:
        header = HEADER.upper() + ",Reviewer"
        rows, issues = parse_manifest_csv(
            _csv(_row(include="true") + ",someone", header=header)
        )

        self.assertEqual(issues, [])
        self.assertEqual([r.file_id for r in rows], ["doc_aaaaaaaaaa"])

    def test_all_nine_system_columns_map_to_canonical_slugs(self) -> None:
        rows, _ = parse_manifest_csv(_csv(_row(ticked=[n for _, n in SYSTEMS])))

        self.assertEqual(
            rows[0].systems,
            [
                "inspire",
                "nurture",
                "trust",
                "embody",
                "guide",
                "regulate",
                "align",
                "transcend",
                "engage",
            ],
        )

    def test_bad_rows_are_skipped_with_issue_codes(self) -> None:
        rows, issues = parse_manifest_csv(
            _csv(
                _row(title=""),
                _row(ticked=()),
                _row(link="see shared drive"),
                _row(title="First"),
                _row(title="Duplicate"),
            )
        )

        self.assertEqual([r.title for r in rows], ["First"])
        self.assertEqual(
            [(i["row"], i["code"]) for i in issues],
            [
                (2, "missing_title"),
                (3, "no_system"),
                (4, "bad_link"),
                (6, "duplicate_file"),
            ],
        )
        self.assertEqual(issues[3]["file_id"], "doc_aaaaaaaaaa")

    def test_issues_carry_the_rows_title_when_it_has_one(self) -> None:
        _, issues = parse_manifest_csv(
            _csv(
                _row(title=""),
                _row(title="Untagged", ticked=()),
                _row(title="Odd Type", doc_type="Memo"),
            )
        )

        self.assertEqual([i.get("title") for i in issues], [None, "Untagged", "Odd Type"])

    def test_reference_rows_need_no_system(self) -> None:
        rows, issues = parse_manifest_csv(
            _csv(_row(doc_type="reference", ticked=("Trust",)), header=HEADER)
        )

        self.assertEqual(issues, [])
        self.assertEqual(rows[0].type, "Reference")
        self.assertEqual(rows[0].systems, [])

        rows, issues = parse_manifest_csv(_csv(_row(doc_type="Reference", ticked=())))
        self.assertEqual(issues, [])
        self.assertEqual(len(rows), 1)

    def test_unknown_type_is_skipped(self) -> None:
        rows, issues = parse_manifest_csv(_csv(_row(doc_type="Memo")))

        self.assertEqual(rows, [])
        self.assertEqual(issues[0]["code"], "bad_type")

    def test_missing_required_column_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_manifest_csv("Title,File\nA,https://drive.google.com/open?id=x\n")


if __name__ == "__main__":
    unittest.main()
