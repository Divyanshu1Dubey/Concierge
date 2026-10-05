"""Undo regex changes and apply correct fix: rows(c, sql, X) -> rows(c, sql, (X,))."""
import re
import glob

for f in glob.glob('src/saas/*.py'):
    with open(f) as fh:
        content = fh.read()

    # Undo: (rows|row)(c, "SQL", tuple(X)) -> (rows|row)(c, "SQL", tuple(X))  [keep as-is for list builds]
    # Undo: (rows|row)(c, "SQL", (X,)) where X is a var -> (rows|row)(c, "SQL", (X,)) [keep as-is]

    # Fix pattern: row/rows(c, sql, single_identifier) -> row/rows(c, sql, (identifier,))
    content = re.sub(
        r'(?<![A-Za-z_])('
        r'rows|row'
        r')\(c,\s*("[^"]*"|\'[^\']*\'),\s*'
        r'([A-Za-z_][A-Za-z0-9_\.]*)\)',
        lambda m: m.group(1) + '(c, ' + m.group(2) + ', (' + m.group(3) + ',))',
        content
    )

    # Fix: multiple single args like row(c, sql, a, b) -> row(c, sql, (a, b))
    content = re.sub(
        r'(?<![A-Za-z_])(rows|row)\(c,\s*("[^"]*"|\'[^\']*\'),\s*([^)]+)\)',
        lambda m: wrap_row_call(m),
        content
    )

    with open(f, 'w') as fh:
        fh.write(content)
    print(f'Fixed: {f}')

def wrap_row_call(m):
    func = m.group(1)
    sql = m.group(2)
    args_str = m.group(3).strip()
    # Skip if already wrapped in () or is tuple() or []
    if args_str.startswith('(') and args_str.endswith(')'):
        return m.group(0)
    if args_str.startswith('tuple(') or args_str.startswith('['):
        return m.group(0)
    # Split on comma and wrap
    return func + '(c, ' + sql + ', (' + args_str + '))'
