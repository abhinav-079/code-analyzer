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

    def test_multilang_2d_arrays_and_ternary(self):
        # C with 2D array and ternary
        c_code = """
        int calc(int m[2][2]) {
            int x = m[0][0];
            return x > 0 ? x : 0;
        }
        int main() {
            int grid[2][2] = {{1, 2}, {3, 4}};
            return calc(grid);
        }
        """
        c_res = analyze_multilang(c_code, language="c")
        self.assertEqual(len(c_res["ast"]["functions"]), 2)
        self.assertEqual(c_res["metrics"]["perFunction"][0]["cyclomatic"], 2)

        # Java with 2D array and ternary
        java_code = """
        public class GridCalc {
            public static int run(int[][] grid, boolean flag) {
                int val = grid[0][1];
                return flag ? val * 2 : val;
            }
        }
        """
        java_res = analyze_multilang(java_code, language="java")
        self.assertEqual(java_res["metrics"]["perFunction"][0]["cyclomatic"], 2)

        # JavaScript with 2D array and ternary
        js_code = """
        function compute(matrix, invert) {
            let cell = matrix[0][0];
            return invert ? -cell : cell;
        }
        """
        js_res = analyze_multilang(js_code, language="javascript")
        self.assertEqual(js_res["metrics"]["perFunction"][0]["cyclomatic"], 2)

        # Python with 2D list and ternary
        py_code = """
        def compute_py(matrix, invert):
            cell = matrix[0][0]
            return -cell if invert else cell
        """
        py_res = analyze_multilang(py_code, language="python")
        self.assertEqual(py_res["metrics"]["perFunction"][0]["cyclomatic"], 2)

    def test_python_top_level_error_detection(self):
        py_code = "a = 3\nprint(ba)\n"
        res = analyze_multilang(py_code, language="python")
        diags = res["diagnostics"]
        errs = [d for d in diags if d["severity"] == "error"]
        warns = [d for d in diags if d["severity"] == "warning"]
        self.assertEqual(len(errs), 1)
        self.assertIn("ba", errs[0]["message"])
        self.assertEqual(errs[0]["rule"], "undeclared-identifier")
        self.assertEqual(len(warns), 1)
        self.assertIn("a", warns[0]["message"])
        self.assertEqual(warns[0]["rule"], "unused-variable")

    def test_cpp_stream_and_undeclared(self):
        cpp_code = """#include <iostream>
int main() {
    int a = 10;
    std::cout << b << std::endl;
    return 0;
}"""
        res = analyze_multilang(cpp_code, language="cpp")
        errs = [d for d in res["diagnostics"] if d["severity"] == "error"]
        self.assertEqual(len(errs), 1)
        self.assertIn("b", errs[0]["message"])

    def test_javascript_top_level_error_detection(self):
        js_code = "let a = 10;\nconsole.log(b);\n"
        res = analyze_multilang(js_code, language="javascript")
        errs = [d for d in res["diagnostics"] if d["severity"] == "error"]
        warns = [d for d in res["diagnostics"] if d["severity"] == "warning"]
        self.assertEqual(len(errs), 1)
        self.assertIn("b", errs[0]["message"])
        self.assertEqual(len(warns), 1)
        self.assertIn("a", warns[0]["message"])

    def test_java_error_detection(self):
        java_code = """public class Test {
    public static void main(String[] args) {
        int a = 10;
        System.out.println(b);
    }
}"""
        res = analyze_multilang(java_code, language="java")
        errs = [d for d in res["diagnostics"] if d["severity"] == "error"]
        warns = [d for d in res["diagnostics"] if d["severity"] == "warning"]
        self.assertEqual(len(errs), 1)
        self.assertIn("b", errs[0]["message"])
        self.assertEqual(len(warns), 1)
        self.assertIn("a", warns[0]["message"])


if __name__ == "__main__":
    unittest.main()
