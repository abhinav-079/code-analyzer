"""
Symbol table management for the Code Quality Analyzer.

Provides scope-aware symbol tracking (Global, Function, and Block scopes).
Tracks symbol names, data types, kind (variable, parameter, function),
declaration locations, and usage references (first-use and all usages).
"""

from typing import Dict, List, Optional, Any


class Symbol:
    def __init__(self, name: str, var_type: str, kind: str, scope_id: int, scope_name: str, line: int = 1, col: int = 1):
        self.name = name
        self.var_type = var_type
        self.kind = kind  # 'variable', 'parameter', 'function'
        self.scope_id = scope_id
        self.scope_name = scope_name
        self.line = line
        self.col = col
        self.references: List[Dict[str, Any]] = []

    @property
    def is_used(self) -> bool:
        return len(self.references) > 0

    @property
    def first_use(self) -> Optional[Dict[str, Any]]:
        return self.references[0] if self.references else None

    def add_reference(self, line: int, col: int, ref_kind: str = "read"):
        self.references.append({"line": line, "col": col, "kind": ref_kind})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.var_type,
            "kind": self.kind,
            "scopeId": self.scope_id,
            "scopeName": self.scope_name,
            "line": self.line,
            "col": self.col,
            "isUsed": self.is_used,
            "usageCount": len(self.references),
            "firstUse": self.first_use,
            "references": self.references,
        }

    def __repr__(self):
        return f"Symbol({self.name}, {self.var_type}, {self.kind}, scope={self.scope_name})"


class Scope:
    def __init__(self, scope_id: int, name: str, scope_type: str = "block", parent: Optional["Scope"] = None, level: int = 0):
        self.scope_id = scope_id
        self.name = name
        self.scope_type = scope_type  # 'global', 'function', 'block'
        self.parent = parent
        self.children: List["Scope"] = []
        self.symbols: Dict[str, Symbol] = {}
        self.level = level

    def define(self, symbol: Symbol) -> bool:
        """Define a symbol in the current scope. Returns False if already defined in this scope."""
        if symbol.name in self.symbols:
            return False
        self.symbols[symbol.name] = symbol
        return True

    def lookup_local(self, name: str) -> Optional[Symbol]:
        """Look up symbol in this scope only."""
        return self.symbols.get(name)

    def lookup(self, name: str) -> Optional[Symbol]:
        """Look up symbol in this scope or enclosing scopes."""
        curr = self
        while curr is not None:
            if name in curr.symbols:
                return curr.symbols[name]
            curr = curr.parent
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scopeId": self.scope_id,
            "name": self.name,
            "scopeType": self.scope_type,
            "level": self.level,
            "parentId": self.parent.scope_id if self.parent else None,
            "symbols": [s.to_dict() for s in self.symbols.values()],
            "children": [c.to_dict() for c in self.children],
        }


class SymbolTable:
    def __init__(self):
        self._next_id = 0
        self.global_scope = Scope(self._get_next_id(), "global", scope_type="global", parent=None, level=0)
        self.current_scope = self.global_scope
        self.all_scopes: List[Scope] = [self.global_scope]

    def _get_next_id(self) -> int:
        idx = self._next_id
        self._next_id += 1
        return idx

    def enter_scope(self, name: str, scope_type: str = "block") -> Scope:
        new_scope = Scope(
            scope_id=self._get_next_id(),
            name=name,
            scope_type=scope_type,
            parent=self.current_scope,
            level=self.current_scope.level + 1,
        )
        self.current_scope.children.append(new_scope)
        self.all_scopes.append(new_scope)
        self.current_scope = new_scope
        return new_scope

    def exit_scope(self) -> Optional[Scope]:
        if self.current_scope.parent is not None:
            self.current_scope = self.current_scope.parent
        return self.current_scope

    def define(self, name: str, var_type: str, kind: str, line: int = 1, col: int = 1) -> tuple[Optional[Symbol], bool]:
        """
        Defines a symbol in the current scope.
        Returns (Symbol, True) if successful, or (ExistingSymbol, False) if duplicate in same scope.
        """
        sym = Symbol(name, var_type, kind, self.current_scope.scope_id, self.current_scope.name, line, col)
        success = self.current_scope.define(sym)
        if not success:
            return self.current_scope.lookup_local(name), False
        return sym, True

    def lookup(self, name: str) -> Optional[Symbol]:
        return self.current_scope.lookup(name)

    def record_usage(self, name: str, line: int, col: int, ref_kind: str = "read") -> Optional[Symbol]:
        sym = self.lookup(name)
        if sym:
            sym.add_reference(line, col, ref_kind)
        return sym

    def get_all_symbols(self) -> List[Symbol]:
        symbols = []
        for scope in self.all_scopes:
            symbols.extend(scope.symbols.values())
        return symbols

    def to_dict(self) -> Dict[str, Any]:
        flat_symbols = [s.to_dict() for s in self.get_all_symbols()]
        return {
            "hierarchy": self.global_scope.to_dict(),
            "flatSymbols": flat_symbols,
            "totalSymbols": len(flat_symbols),
            "totalScopes": len(self.all_scopes),
        }
