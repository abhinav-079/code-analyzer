import unittest
from app import app


class TestAPI(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_get_index(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Code Quality Analyzer", resp.data)

    def test_post_analyze_valid(self):
        resp = self.client.post("/analyze", json={"code": "int main() { return 0; }"})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("tokens", data)
        self.assertIn("ast", data)
        self.assertIn("metrics", data)
        self.assertIn("cfgs", data)
        self.assertIn("symbolTable", data)
        self.assertIn("diagnostics", data)
        self.assertIn("quality", data)

    def test_post_analyze_syntax_error(self):
        resp = self.client.post("/analyze", json={"code": "int main() { invalid @; }"})
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn("error", data)

    def test_post_analyze_project(self):
        resp = self.client.post("/analyze_project", json={
            "files": [
                {"name": "a.c", "code": "int a() { return 1; }"},
                {"name": "b.c", "code": "int b() { return 2; }"}
            ]
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["summary"]["fileCount"], 2)
        self.assertEqual(len(data["files"]), 2)


if __name__ == "__main__":
    unittest.main()
