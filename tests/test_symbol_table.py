import unittest
from compiler.symbol_table import SymbolTable


class TestSymbolTable(unittest.TestCase):
    def test_scope_nesting_and_lookup(self):
        st = SymbolTable()
        # Global scope
        st.define("g", "int", "variable", line=1, col=1)

        # Function scope
        st.enter_scope("main", scope_type="function")
        st.define("x", "float", "variable", line=2, col=5)

        # Lookup x in function scope
        sym_x = st.lookup("x")
        self.assertIsNotNone(sym_x)
        self.assertEqual(sym_x.var_type, "float")

        # Lookup g in function scope (searches up to global)
        sym_g = st.lookup("g")
        self.assertIsNotNone(sym_g)
        self.assertEqual(sym_g.var_type, "int")

        # Exit function scope
        st.exit_scope()
        self.assertIsNone(st.lookup("x"))

    def test_shadowing(self):
        st = SymbolTable()
        st.define("val", "int", "variable", line=1, col=1)

        st.enter_scope("inner", scope_type="block")
        st.define("val", "double", "variable", line=3, col=5)
        self.assertEqual(st.lookup("val").var_type, "double")

        st.exit_scope()
        self.assertEqual(st.lookup("val").var_type, "int")

    def test_duplicate_definition_same_scope(self):
        st = SymbolTable()
        _, ok1 = st.define("x", "int", "variable", line=1, col=1)
        _, ok2 = st.define("x", "int", "variable", line=2, col=1)
        self.assertTrue(ok1)
        self.assertFalse(ok2)

    def test_usage_tracking(self):
        st = SymbolTable()
        st.define("counter", "int", "variable", line=1, col=1)
        sym = st.lookup("counter")
        self.assertFalse(sym.is_used)

        st.record_usage("counter", line=5, col=10)
        self.assertTrue(sym.is_used)
        self.assertEqual(sym.first_use["line"], 5)


if __name__ == "__main__":
    unittest.main()
