import unittest
from compiler.lexer import tokenize, Token


class TestLexer(unittest.TestCase):
    def test_basic_tokenization(self):
        code = "int x = 42;"
        tokens = tokenize(code)
        types = [t.type for t in tokens if t.type != "EOF"]
        values = [t.value for t in tokens if t.type != "EOF"]
        self.assertEqual(types, ["KEYWORD", "IDENTIFIER", "OPERATOR", "NUMBER", "DELIMITER"])
        self.assertEqual(values, ["int", "x", "=", "42", ";"])

    def test_line_and_col_tracking(self):
        code = "int a;\nint b = 10;"
        tokens = tokenize(code)
        # Token 'a' on line 1
        t_a = tokens[1]
        self.assertEqual(t_a.value, "a")
        self.assertEqual(t_a.line, 1)
        self.assertEqual(t_a.col, 5)

        # Token 'b' on line 2
        t_b = tokens[4]
        self.assertEqual(t_b.value, "b")
        self.assertEqual(t_b.line, 2)
        self.assertEqual(t_b.col, 5)

    def test_preprocessor_directive(self):
        code = "#include <stdio.h>\n#define MAX 100\nint main() {}"
        tokens = tokenize(code)
        self.assertEqual(tokens[0].type, "PREPROCESSOR")
        self.assertEqual(tokens[0].value, "#include <stdio.h>")
        self.assertEqual(tokens[1].type, "PREPROCESSOR")
        self.assertEqual(tokens[1].value, "#define MAX 100")

    def test_comments(self):
        code = """
        // line comment
        int x = 1; /* block comment */
        int y = 2;
        """
        tokens = tokenize(code)
        vars_found = [t.value for t in tokens if t.type == "IDENTIFIER"]
        self.assertEqual(vars_found, ["x", "y"])

    def test_operators_and_delimiters(self):
        code = "a += 1; b == 2 && c <= 3 || d != 4; *p; &val; arr[0];"
        tokens = tokenize(code)
        ops = [t.value for t in tokens if t.type == "OPERATOR"]
        self.assertIn("+=", ops)
        self.assertIn("==", ops)
        self.assertIn("&&", ops)
        self.assertIn("<=", ops)
        self.assertIn("||", ops)
        self.assertIn("!=", ops)
        self.assertIn("*", ops)
        self.assertIn("&", ops)

    def test_syntax_error_position(self):
        code = "int x = 10 @ 5;"
        with self.assertRaises(SyntaxError) as ctx:
            tokenize(code)
        self.assertIn("Unexpected character '@' at line 1", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
