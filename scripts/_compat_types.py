"""Reescribe sintaxis de tipos para que el código sea Python 3.9+ compatible.

PEP 604 (X | None) y PEP 585 (list[X], dict[K,V]) son sintaxis válida en
RUNTIME solo a partir de 3.10 / 3.9 respectivamente. SQLAlchemy 2.x y
Pydantic v2 evalúan las annotations en runtime → fallan en 3.9.

Esta utilidad reescribe:
    str | None        →  Optional[str]
    list[X]           →  List[X]
    dict[K, V]        →  Dict[K, V]
    tuple[X, ...]     →  Tuple[X, ...]
y agrega los imports necesarios desde typing.

Una vez transformado, el código corre OK en 3.9 → 3.13.
"""
import re
import sys
from pathlib import Path


def transform(src: str) -> str:
    original = src
    # Solo si el archivo no parece ya transformado
    needs_optional = bool(re.search(r"\|\s*None\b", src))
    needs_generic = bool(re.search(r"\b(list|dict|tuple|set|frozenset)\[", src))

    # X | None → Optional[X] (X puede ser un tipo simple o con [])
    # Atajamos casos comunes con tipo "atómico" o con un nivel de [ ]
    def replace_union_none(s: str) -> str:
        # tipo con subscripts no anidados a la izquierda
        # ej. "list[Imagen] | None"  → "Optional[list[Imagen]]"
        # ej. "str | None"           → "Optional[str]"
        pattern = re.compile(r"([A-Za-z_][\w.]*(?:\[[^\[\]]*\])?)\s*\|\s*None\b")
        prev = None
        while prev != s:
            prev = s
            s = pattern.sub(r"Optional[\1]", s)
        return s

    src = replace_union_none(src)

    # list[X] → List[X], dict[K,V] → Dict[K,V], tuple → Tuple, set → Set
    for low, up in [("list", "List"), ("dict", "Dict"), ("tuple", "Tuple"),
                    ("set", "Set"), ("frozenset", "FrozenSet")]:
        src = re.sub(rf"\b{low}\[", f"{up}[", src)

    # Agregar imports si hace falta
    needs = set()
    if "Optional[" in src and "Optional" not in re.findall(r"from typing import.*", src + ""):
        needs.add("Optional")
    for name in ("List", "Dict", "Tuple", "Set", "FrozenSet"):
        if f"{name}[" in src:
            needs.add(name)
    # Filtrar lo que ya está importado
    existing = set()
    for m in re.finditer(r"from typing import (.+)", src):
        for n in m.group(1).split(","):
            existing.add(n.strip())
    to_add = sorted(needs - existing)
    if to_add:
        line = f"from typing import {', '.join(to_add)}\n"
        # insertar después del bloque inicial de imports / docstring / __future__
        lines = src.splitlines(keepends=True)
        insert_at = 0
        # saltear docstring
        if lines and lines[0].lstrip().startswith(('"""', "'''")):
            quote = '"""' if lines[0].lstrip().startswith('"""') else "'''"
            if lines[0].count(quote) >= 2:
                insert_at = 1
            else:
                for i, ln in enumerate(lines[1:], 1):
                    if quote in ln:
                        insert_at = i + 1
                        break
        # saltear __future__
        while insert_at < len(lines) and lines[insert_at].startswith("from __future__"):
            insert_at += 1
        lines.insert(insert_at, line)
        src = "".join(lines)

    return src if src != original else original


def main():
    root = Path(__file__).resolve().parent.parent
    changed = []
    for p in (root / "app").rglob("*.py"):
        new = transform(p.read_text())
        if new != p.read_text():
            p.write_text(new)
            changed.append(str(p.relative_to(root)))
    print(f"Transformados: {len(changed)}")
    for c in changed:
        print("  ·", c)


if __name__ == "__main__":
    main()
