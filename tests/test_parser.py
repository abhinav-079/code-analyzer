import unittest
from compiler.lexer import tokenize
from compiler.parser import Parser, ParseError


class TestParser(unittest.TestCase):
    def test_parse_simple_function(self):
        code = "int main() { return 0; }"
        tokens = tokenize(code)
        ast = Parser(tokens).parse_program()
        self.assertEqual(len(ast["functions"]), 1)
        fn = ast["functions"][0]
        self.assertEqual(fn["name"], "main")
        self.assertEqual(fn["returnType"], "int")
        self.assertEqual(len(fn["body"]["statements"]), 1)
        self.assertEqual(fn["body"]["statements"][0]["type"], "Return")

    def test_parse_if_else(self):
        code = """
        int test(int a) {
            if (a > 0) {
                return 1;
            } else {
                return -1;
            }
        }
        """
        tokens = tokenize(code)
        ast = Parser(tokens).parse_program()
        stmt = ast["functions"][0]["body"]["statements"][0]
        self.assertEqual(stmt["type"], "If")
        self.assertIsNotNone(stmt["consequent"])
        self.assertIsNotNone(stmt["alternate"])

    def test_parse_switch_case(self):
        code = """
        int evaluate(int val) {
            switch (val) {
                case 1:
                    return 10;
                case 2:
                    return 20;
                default:
                    return 0;
            }
        }
        """
        tokens = tokenize(code)
        ast = Parser(tokens).parse_program()
        stmt = ast["functions"][0]["body"]["statements"][0]
        self.assertEqual(stmt["type"], "Switch")
        self.assertEqual(len(stmt["cases"]), 3)
        self.assertEqual(stmt["cases"][0]["type"], "Case")
        self.assertEqual(stmt["cases"][2]["type"], "Default")

    def test_parse_pointers_and_arrays(self):
        code = """
        void process(int *ptr, int arr[]) {
            int x = *ptr;
            arr[0] = x;
        }
        """
        tokens = tokenize(code)
        ast = Parser(tokens).parse_program()
        stmts = ast["functions"][0]["body"]["statements"]
        self.assertEqual(stmts[0]["type"], "Declaration")
        self.assertEqual(stmts[0]["init"]["type"], "PointerDeref")
        self.assertEqual(stmts[1]["type"], "ExprStmt")
        self.assertEqual(stmts[1]["expr"]["type"], "Assign")
        self.assertEqual(stmts[1]["expr"]["target"]["type"], "ArrayAccess")

    def test_parse_loops(self):
        code = """
        void loops() {
            for (int i = 0; i < 10; i++) {
                break;
            }
            while (1) {
                continue;
            }
            do {
                int z = 1;
            } while (0);
        }
        """
        tokens = tokenize(code)
        ast = Parser(tokens).parse_program()
        stmts = ast["functions"][0]["body"]["statements"]
        self.assertEqual(stmts[0]["type"], "For")
        self.assertEqual(stmts[1]["type"], "While")
        self.assertEqual(stmts[2]["type"], "DoWhile")

    def test_parse_error_reporting(self):
        code = "int main() { int x = ; }"
        tokens = tokenize(code)
        with self.assertRaises(ParseError) as ctx:
            Parser(tokens).parse_program()
        self.assertIn("Line 1", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
