"""Static frontend contract tests for selectors, views and listener targets."""
from __future__ import annotations

import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "app" / "static" / "index.html"
JS_PATH = ROOT / "app" / "static" / "app.js"


class MarkupInventory(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.view_names: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(values["id"])
        if values.get("data-view"):
            self.view_names.append(values["data-view"])


class FrontendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML_PATH.read_text(encoding="utf-8")
        cls.js = JS_PATH.read_text(encoding="utf-8")
        parser = MarkupInventory()
        parser.feed(cls.html)
        cls.ids = parser.ids
        cls.id_set = set(parser.ids)
        cls.views = set(parser.view_names)

    def test_html_ids_are_unique(self):
        duplicates = sorted({item for item in self.ids if self.ids.count(item) > 1})
        self.assertEqual(duplicates, [], f"Duplicate HTML IDs: {duplicates}")

    def test_direct_javascript_id_selectors_exist(self):
        referenced = set(re.findall(r"""\$\(["']#([A-Za-z0-9_-]+)["']\)""", self.js))
        missing = sorted(referenced - self.id_set)
        self.assertEqual(missing, [], f"Selectors reference missing IDs: {missing}")

    def test_event_listener_targets_exist(self):
        targets = set(re.findall(r"""\$\(["']#([A-Za-z0-9_-]+)["']\)\.addEventListener""", self.js))
        missing = sorted(targets - self.id_set)
        self.assertEqual(missing, [], f"Event listeners target missing IDs: {missing}")

    def test_collection_methods_use_multi_element_selector(self):
        # $() is querySelector; $$() is querySelectorAll. Calling .forEach/.map
        # on a single Element aborts startup or a feature action at runtime.
        bad = re.findall(
            r"""(?<!\$)\$\([^;\n]*?\)\.(?:forEach|map|filter|some|every|reduce)\s*\(""",
            self.js,
        )
        self.assertEqual(bad, [], f"Single-element selector used as a collection: {bad}")

    def test_navigation_views_have_matching_sections(self):
        expected = {
            "browse": "browseView",
            "report": "reportView",
            "my-reports": "myReportsView",
            "my-claims": "myClaimsView",
            "notifications": "notificationsView",
            "activity": "activityView",
            "office": "officeView",
        }
        missing = [view for view in self.views if expected.get(view) not in self.id_set]
        self.assertEqual(missing, [], f"Navigation views missing their section: {missing}")
        self.assertTrue(set(expected).issubset(self.views))

    def test_live_notification_polling_is_enabled(self):
        self.assertIn("startNotificationPolling();", self.js)
        self.assertIn("}, 10000);", self.js)
        self.assertIn("stopNotificationPolling();", self.js)


if __name__ == "__main__":
    unittest.main()
