import importlib.util
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "import_maroon_docx.py"
SPEC = importlib.util.spec_from_file_location("import_maroon_docx", SCRIPT_PATH)
import_maroon_docx = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(import_maroon_docx)


class ImportMaroonDocxTests(unittest.TestCase):
    def test_extracts_all_docx_records(self):
        docx = Path(__file__).resolve().parents[1] / "Maroon Plaque Location and Text List 2025.docx"
        chunks = import_maroon_docx.extract_docx_chunks(docx)
        self.assertEqual(len(chunks), 29)

    def test_fallback_records_identify_openplaques_gaps(self):
        docx = Path(__file__).resolve().parents[1] / "Maroon Plaque Location and Text List 2025.docx"
        records = import_maroon_docx.records_from_docx(docx, {"features": []})
        self.assertEqual(
            {record["title"] for record in records},
            {"Black People\u2019s Day of Action", "Young Lives Lost in the New Cross Fire of 1981"},
        )
        self.assertTrue(all(record["kind"] == "plaque" for record in records))
        self.assertTrue(all(record["collection"] == "lewisham-maroon" for record in records))
        self.assertTrue(all(record["curation_status"] == "in_scope" for record in records))


if __name__ == "__main__":
    unittest.main()
