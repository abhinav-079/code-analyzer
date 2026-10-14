import unittest
from compiler.multi_language import detect_language, analyze_multilang


class TestMultiLanguage(unittest.TestCase):
    def test_detect_language_by_filename(self):
        self.assertEqual(detect_language("", "script.py"), "python")
        self.assertEqual(detect_language("", "App.java"), "java")
        self.assertEqual(detect_language("", "bundle.js"), "javascript")
        self.assertEqual(detect_language("", "service.cpp"), "cpp")
        self.assertEqual(detect_language("", "main.c"), "c")

    def test_detect_language_by_content(self):
        self.assertEqual(detect_language("def calculate(x):\n    return x"), "python")
        self.assertEqual(detect_language("public class Test {\n    int a;\n}"), "java")
        self.assertEqual(detect_language("function process() {\n    console.log('hi');\n}"), "javascript")
        self.assertEqual(detect_language("#include <iostream>\nusing namespace std;\nint main() {}"), "cpp")

    def test_python_analysis(self):
        code = """
def test_calc(n):
    total = 0
    unused_var = 1
    for i in range(n):
        if i % 2 == 0:
            total += i
    return total
"""
        res = analyze_multilang(code, language="python")
        self.assertEqual(res["language"], "python")
        self.assertEqual(len(res["metrics"]["perFunction"]), 1)
        self.assertEqual(res["metrics"]["perFunction"][0]["name"], "test_calc")
        self.assertEqual(res["metrics"]["perFunction"][0]["cyclomatic"], 3)  # 1 base + 1 for + 1 if
        self.assertIn("test_calc", res["cfgs"])
        self.assertTrue(len(res["diagnostics"]) >= 1)

    def test_java_analysis(self):
        code = """
public class Solution {
    public static int add(int a, int b) {
        if (a > 0) return a + b;
        return b;
    }
}
"""
        res = analyze_multilang(code, language="java")
        self.assertEqual(res["language"], "java")
        self.assertEqual(len(res["metrics"]["perFunction"]), 1)
        self.assertEqual(res["metrics"]["perFunction"][0]["cyclomatic"], 2)

    def test_javascript_analysis(self):
        code = """
function process(val) {
    let result = 0;
    while (val > 0) {
        result += val;
        val--;
    }
    return result;
}
"""
        res = analyze_multilang(code, language="javascript")
        self.assertEqual(res["language"], "javascript")
        self.assertEqual(len(res["metrics"]["perFunction"]), 1)
        self.assertEqual(res["metrics"]["perFunction"][0]["cyclomatic"], 2)

    def test_cpp_analysis(self):
        code = """
class MathService {
public:
    int square(int x) {
        return x * x;
    }
};
int main() {
    return 0;
}
"""
        res = analyze_multilang(code, language="cpp")
        self.assertEqual(res["language"], "cpp")
        self.assertEqual(len(res["metrics"]["perFunction"]), 2)


if __name__ == "__main__":
    unittest.main()
