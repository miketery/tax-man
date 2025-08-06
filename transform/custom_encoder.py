import json

class NoIndent:
    def __init__(self, value):
        self.value = ",".join(value)

class FlatRow:
    def __init__(self, value):
        self.value = json.dumps(value)

class CustomEncoder(json.JSONEncoder):
    def default(self, o):
        # if isinstance(o, NoIndent):
        #     return '["' + '", "'.join(o.value.split(",")) + '"]'
        if isinstance(o, FlatRow):
            x = json.loads(o.value)
            z = [f"{y[0]}, {y[1]}" for y in x]
            return ', '.join(z)
        return super().default(o)

    def iterencode(self, o, _one_shot=False):
        if self.indent is None:
            return super().iterencode(o, _one_shot)

        def _iterencode(o, current_indent):
            if isinstance(o, FlatRow):
                yield o.value
            elif isinstance(o, (list, tuple)):
                if not o:
                    yield '[]'
                    return
                yield '['
                next_indent = current_indent + self.indent
                first = True
                for value in o:
                    if not first:
                        yield ','
                    yield ' ' * next_indent
                    yield from _iterencode(value, next_indent)
                    first = False
                yield' ' * current_indent + ']'
            elif isinstance(o, dict):
                if not o:
                    yield '{}'
                    return
                yield '{'
                next_indent = current_indent + self.indent
                first = True
                for key, value in o.items():
                    if not first:
                        yield ','
                    yield '\n' + ' ' * next_indent
                    yield json.dumps(key) + ': '
                    yield from _iterencode(value, next_indent)
                    first = False
                yield '\n' + ' ' * current_indent + '}'
            else:
                yield json.dumps(o, ensure_ascii=self.ensure_ascii)

        return _iterencode(o, 0)