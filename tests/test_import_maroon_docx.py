import importlib.util
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "import_maroon_docx.py"
SPEC = importlib.util.spec_from_file_location("import_maroon_docx", SCRIPT_PATH)
import_maroon_docx = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(import_maroon_docx)


class ImportMaroonDocxTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.docx = Path(self.temp_dir.name) / "maroon-plaques.docx"
        paragraphs = []
        for index in range(1, 30):
            title = {
                17: "Black People’s Day of Action",
                29: "Young Lives Lost in the New Cross Fire of 1981",
            }.get(index, f"Plaque {index}")
            paragraphs.append(
                f"<w:p><w:r><w:t>{title}</w:t><w:br/><w:t>Address {index}</w:t>"
                f"<w:br/><w:t>Description {index}</w:t></w:r></w:p>"
            )
        document = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body>{''.join(paragraphs)}</w:body></w:document>"
        )
        with ZipFile(self.docx, "w") as archive:
            archive.writestr("word/document.xml", document)

    def test_extracts_all_docx_records(self):
        chunks = import_maroon_docx.extract_docx_chunks(self.docx)
        self.assertEqual(len(chunks), 29)

    def test_fallback_records_identify_openplaques_gaps(self):
        records = import_maroon_docx.records_from_docx(self.docx, {"features": []})
        self.assertEqual(
            {record["title"] for record in records},
            {"Black People\u2019s Day of Action", "Young Lives Lost in the New Cross Fire of 1981"},
        )
        self.assertTrue(all(record["kind"] == "plaque" for record in records))
        self.assertTrue(all(record["collection"] == "lewisham-maroon" for record in records))
        self.assertTrue(all(record["curation_status"] == "in_scope" for record in records))
        self.assertTrue(
            all(record["attributes"]["source_document_url"] == import_maroon_docx.SOURCE_DOCUMENT_URL for record in records)
        )


if __name__ == "__main__":
    unittest.main()
