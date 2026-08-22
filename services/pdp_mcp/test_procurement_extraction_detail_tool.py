from pathlib import Path
import re
import unittest


class ProcurementExtractionDetailToolContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path(__file__).with_name("procurement_tools.py").read_text(encoding="utf-8")

    def test_completed_run_detail_tool_is_read_only_and_get_only(self):
        pattern = re.compile(
            r"annotations=ToolAnnotations\(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True\),"
            r"\s*\)\s*async def get_procurement_extraction_run_detail\(run_id: str\) -> dict:"
            r"\s*return await api\(\"GET\", f\"procurement/extraction-runs/\{run_id\}/\"\)",
            re.MULTILINE,
        )
        self.assertRegex(self.source, pattern)

    def test_tool_does_not_add_an_extraction_write_call(self):
        start = self.source.index("async def get_procurement_extraction_run_detail")
        end = self.source.index("\n\n    @mcp.tool", start)
        block = self.source[start:end]
        self.assertNotIn('api("POST"', block)
        self.assertNotIn('api("PATCH"', block)
        self.assertNotIn('api("DELETE"', block)


if __name__ == "__main__":
    unittest.main()
