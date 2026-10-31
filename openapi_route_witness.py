#!/usr/bin/env python3
"""Bounded JSON OpenAPI route intersections. Python 3.11+, standard library only."""
import json
import math
import re
import sys

MAX_BYTES = 1_048_576
MAX_DEPTH = 64
MAX_NODES = 100_000
MAX_PATHS = 500
MAX_PAIRS = 124_750
MAX_SEGMENTS = 64
MAX_PATH_LENGTH = 4096
MAX_FINDINGS = 10_000
METHODS = ('get', 'put', 'post', 'delete', 'options', 'head', 'patch', 'trace')
UNRESERVED = re.compile(r'[A-Za-z0-9._~-]+\Z')
VERSION = re.compile(r'3\.[01]\.[0-9]+\Z')
HELP = '''Usage: python openapi_route_witness.py FILE.json
       python openapi_route_witness.py -
       python openapi_route_witness.py --help
Read bounded UTF-8 JSON from a file or stdin; emit one JSON report.
Exit 0: no errors (info permitted); 1: route findings; 2: invalid/unsupported/I/O.
Witnesses disclose input path literal segments. See README.md for limits.
'''


class InputError(Exception):
    """Only a fixed neutral code is safe for output."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError('invalid_json')
        result[key] = value
    return result


def _nonfinite(_value):
    raise InputError('invalid_json')


def _decode(data):
    if len(data) > MAX_BYTES:
        raise InputError('bounds_exceeded')
    try:
        text = data.decode('utf-8')
        # Bound nesting before the recursive stdlib decoder, respecting strings.
        depth, quoted, escaped = 0, False, False
        for char in text:
            if quoted:
                if escaped:
                    escaped = False
                elif char == '\\':
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in '{[':
                depth += 1
                if depth > MAX_DEPTH:
                    raise InputError('bounds_exceeded')
            elif char in '}]':
                depth -= 1
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_nonfinite)
    except (UnicodeError, ValueError, RecursionError):
        raise InputError('invalid_json') from None
    stack = [(value, 1)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            raise InputError('bounds_exceeded')
        if isinstance(current, str) and any(0xD800 <= ord(c) <= 0xDFFF for c in current):
            raise InputError('invalid_json')
        if isinstance(current, float) and not math.isfinite(current):
            raise InputError('invalid_json')
        if isinstance(current, dict):
            for key, child in current.items():
                stack.append((key, depth + 1))
                stack.append((child, depth + 1))
        elif isinstance(current, list):
            stack.extend((child, depth + 1) for child in current)
    return value


def _segments(path):
    if len(path) > MAX_PATH_LENGTH:
        raise InputError('bounds_exceeded')
    if not path.startswith('/'):
        raise InputError('unsupported_path')
    parts = path[1:].split('/')
    if len(parts) > MAX_SEGMENTS:
        raise InputError('bounds_exceeded')
    result = []
    for index, part in enumerate(parts):
        # Only root or a single final empty segment is supported.
        if not part:
            if index != len(parts) - 1 or (len(parts) > 1 and not parts[index - 1]):
                raise InputError('unsupported_path')
            result.append('')
        elif part.startswith('{') and part.endswith('}') and UNRESERVED.fullmatch(part[1:-1]):
            result.append(None)
        elif UNRESERVED.fullmatch(part):
            result.append(part)
        else:
            raise InputError('unsupported_path')
    return tuple(result)


def _intersection(left, right):
    """Return a witness and which side adds literal restrictions, or None."""
    if len(left) != len(right):
        return None
    witness = []
    left_stricter = right_stricter = False
    for a, b in zip(left, right):
        if a is None and b is None:
            witness.append('example')
        elif a is None:
            if b == '':
                return None
            witness.append(b)
            right_stricter = True
        elif b is None:
            if a == '':
                return None
            witness.append(a)
            left_stricter = True
        elif a != b:
            return None
        else:
            witness.append(a)
    return '/' + '/'.join(witness), left_stricter, right_stricter


def inspect_bytes(data):
    """Analyze UTF-8 JSON bytes or raise InputError; no files or network access."""
    value = _decode(data)
    if not isinstance(value, dict) or 'openapi' not in value:
        raise InputError('invalid_document')
    version = value.get('openapi')
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        raise InputError('unsupported_version')
    paths = value.get('paths')
    if not isinstance(paths, dict):
        raise InputError('invalid_document')
    routes = []
    for path, path_item in paths.items():
        if path.startswith('x-'):
            continue
        if len(routes) >= MAX_PATHS:
            raise InputError('bounds_exceeded')
        segments = _segments(path)
        if not isinstance(path_item, dict):
            raise InputError('invalid_document')
        if '$ref' in path_item:
            raise InputError('unsupported_reference')
        methods = []
        for method in METHODS:
            if method in path_item:
                if not isinstance(path_item[method], dict):
                    raise InputError('invalid_document')
                methods.append(method)
        routes.append((segments, methods))
    pairs_count = len(routes) * (len(routes) - 1) // 2
    if pairs_count > MAX_PAIRS:
        raise InputError('bounds_exceeded')
    findings = []
    pair_index = 0
    for i, (left, left_methods) in enumerate(routes):
        for j in range(i + 1, len(routes)):
            right, right_methods = routes[j]
            intersection = _intersection(left, right)
            if intersection:
                witness, a_stricter, b_stricter = intersection
                common = [m for m in METHODS if m in left_methods and m in right_methods]
                equivalent = left == right and None in left
                if equivalent:
                    methods = [None]  # A Paths-level invalidity, independent of HTTP method.
                    code, severity = 'equivalent_template', 'error'
                elif a_stricter and b_stricter:
                    methods = common
                    code, severity = 'crossing_overlap', 'error'
                else:
                    methods = common
                    code, severity = 'specific_precedence', 'info'
                for method in methods:
                    finding = dict(code=code, severity=severity, path_indices=[i, j],
                                   pair_index=pair_index, method=method, witness=witness)
                    if code == 'specific_precedence':
                        finding['preferred_path_index'] = i if a_stricter else j
                    findings.append(finding)
                    if len(findings) > MAX_FINDINGS:
                        raise InputError('bounds_exceeded')
            pair_index += 1
    return dict(profile='ascii-segment-v1', path_count=len(routes), pairs_checked=pairs_count,
                findings=findings, exit_code=int(any(f['severity'] == 'error' for f in findings)))


def _write(text):
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
        return True
    except (OSError, UnicodeError, ValueError):
        # Do not let interpreter shutdown retry a failed buffered flush.
        sys.stdout = None
        return False


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args in (['--help'], ['-h']):
        return 0 if _write(HELP) else 2
    try:
        if len(args) != 1 or (args[0].startswith('-') and args[0] != '-'):
            raise InputError('invalid_arguments')
        try:
            if args[0] == '-':
                data = sys.stdin.buffer.read(MAX_BYTES + 1)
            else:
                with open(args[0], 'rb') as source:
                    data = source.read(MAX_BYTES + 1)
        except (OSError, ValueError, UnicodeError):
            raise InputError('io_error') from None
        result = inspect_bytes(data)
        status = result['exit_code']
    except InputError as error:
        result, status = {'error': {'code': error.code}}, 2
    return status if _write(json.dumps(result, ensure_ascii=True, separators=(',', ':')) + '\n') else 2


if __name__ == '__main__':
    raise SystemExit(main())
