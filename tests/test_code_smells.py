import unittest
from compiler.lexer import tokenize
from compiler.parser import Parser
from compiler.analyzer import analyze


class TestCodeSmells(unittest.TestCase):
    def test_deep_nesting_smell(self):
        code = """
        void deep(int a, int b, int c, int d) {
            if (a > 0) {
                if (b > 0) {
                    if (c > 0) {
                        if (d > 0) {
                            return;
                        }
                    }
                }
            }
        }
        """
        tokens = tokenize(code)
        ast = Parser(tokens).parse_program()
        res = analyze(ast, 12)
        smell_categories = [s["category"] for s in res["codeSmells"]]
        self.assertIn("Deep Nesting", smell_categories)

    def test_unreachable_code_smell(self):
        code = """
        int dead() {
            return 1;
            int x = 2; // Dead code
        }
        """
        tokens = tokenize(code)
        ast = Parser(tokens).parse_program()
        res = analyze(ast, 5)
        smell_categories = [s["category"] for s in res["codeSmells"]]
        self.assertIn("Dead / Unreachable Code", smell_categories)

    def test_unused_variable_smell(self):
        code = """
        void test() {
            int ghost = 100;
        }
        """
        tokens = tokenize(code)
        ast = Parser(tokens).parse_program()
        res = analyze(ast, 3)
        smell_categories = [s["category"] for s in res["codeSmells"]]
        self.assertIn("Unused Variable", smell_categories)


if __name__ == "__main__":
    unittest.main()
