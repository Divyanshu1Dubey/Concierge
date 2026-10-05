"""Fix row/rows calls to wrap single args in tuples."""
import re
import glob

for f in glob.glob('src/saas/*.py'):
    with open(f) as fh:
        content = fh.read()

    # Fix: row(c, sql, X) where X is a single variable/call -> row(c, sql, (X,))
    # Skip if already has parens, tuple(), or list
    def wrap_single_arg(m):
        full = m.group(0)
        args = m.group(3)
        if args.startswith('(') or args.startswith('tuple(') or args.startswith('['):
            return full
        return m.group(1) + '(c, ' + m.group(2) + ', (' + args + ',))'

    content = re.sub(
        r'(rows|row)\(c,\s*("[^"]*"|\'[^\']*\'),\s*([A-Za-z_][A-Za-z0-9_\.]*(?:\([^)]*\))?)\)',
        wrap_single_arg,
        content
    )

    with open(f, 'w') as fh:
        fh.write(content)
    print(f'Fixed: {f}')
