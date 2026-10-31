"""Behavior contracts; independent witness checker never calls route internals."""
import importlib.util
import io
import itertools
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'openapi_route_witness.py'
if SCRIPT.exists():
    spec = importlib.util.spec_from_file_location('route_checker', SCRIPT)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
else:
    tool = None


def document(paths, **extra):
    return dict(openapi='3.1.1', paths=paths, **extra)


def item(*methods):
    return {m: {'responses': {'200': {'description': 'Synthetic response'}}} for m in methods}


def accepts(pattern, witness):
    # A separate test oracle: no imports from the implementation.
    left, right = pattern.split('/')[1:], witness.split('/')[1:]
    return len(left) == len(right) and all(
        bool(value) if part.startswith('{') and part.endswith('}') else part == value
        for part, value in zip(left, right)
    )


class Routes(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(tool, 'route implementation is missing')

    def inspect(self, paths, **extra):
        return tool.inspect_bytes(json.dumps(document(paths, **extra)).encode())

    def invalid(self, data, code=None):
        with self.assertRaises(tool.InputError) as caught:
            tool.inspect_bytes(data)
        if code:
            self.assertEqual(code, caught.exception.code)

    def test_crossing_returns_concrete_witness(self):
        result = self.inspect({'/{entity}/me': item('get'), '/books/{id}': item('get')})
        self.assertEqual(1, result['exit_code'])
        self.assertEqual([{'code': 'crossing_overlap', 'severity': 'error', 'path_indices': [0, 1],
                           'pair_index': 0, 'method': 'get', 'witness': '/books/me'}], result['findings'])

    def test_equivalent_templates_invalid_across_methods(self):
        result = self.inspect({'/pets/{id}': item('get'), '/pets/{name}': item('post')})
        self.assertEqual(1, result['exit_code'])
        self.assertEqual('equivalent_template', result['findings'][0]['code'])
        self.assertIsNone(result['findings'][0]['method'])

    def test_empty_path_items_still_duplicate(self):
        self.assertEqual(1, self.inspect({'/{a}': {}, '/{b}': {}})['exit_code'])

    def test_concrete_precedence_is_info(self):
        result = self.inspect({'/pets/{id}': item('get'), '/pets/mine': item('get')})
        self.assertEqual(0, result['exit_code'])
        self.assertEqual('specific_precedence', result['findings'][0]['code'])
        self.assertEqual('info', result['findings'][0]['severity'])
        self.assertEqual(1, result['findings'][0]['preferred_path_index'])

    def test_partial_template_dominance(self):
        result = self.inspect({'/{a}/{b}': item('get'), '/books/{id}': item('get')})
        self.assertEqual(0, result['exit_code'])
        self.assertEqual('/books/example', result['findings'][0]['witness'])

    def test_literal_count_alone_does_not_establish_dominance(self):
        result = self.inspect({'/books/{id}/{kind}': item('get'), '/{entity}/me/new': item('get')})
        self.assertEqual('crossing_overlap', result['findings'][0]['code'])

    def test_different_methods_crossing_ignored(self):
        self.assertEqual([], self.inspect({'/{a}/me': item('get'), '/books/{id}': item('post')})['findings'])

    def test_each_shared_known_method_reported(self):
        result = self.inspect({'/{a}/me': item('get', 'head', 'trace'), '/books/{id}': item('get', 'head', 'trace')})
        self.assertEqual(['get', 'head', 'trace'], [f['method'] for f in result['findings']])

    def test_no_get_to_head_fallback(self):
        self.assertEqual([], self.inspect({'/{a}/me': item('get'), '/books/{id}': item('head')})['findings'])

    def test_case_sensitive_literals(self):
        self.assertEqual([], self.inspect({'/Books': item('get'), '/books': item('get')})['findings'])

    def test_metadata_extensions_not_operations(self):
        paths = {'x-note': ['private'], '/{a}/me': {'summary': 'SECRET', 'GET': {}, 'x-get': {}}, '/books/{id}': item('get')}
        self.assertEqual([], self.inspect(paths)['findings'])

    def test_root_does_not_match_nonempty_parameter(self):
        self.assertEqual([], self.inspect({'/': item('get'), '/{id}': item('get')})['findings'])

    def test_trailing_slash_distinct(self):
        self.assertEqual([], self.inspect({'/pets': item('get'), '/pets/': item('get')})['findings'])

    def test_trailing_empty_does_not_match_parameter(self):
        self.assertEqual([], self.inspect({'/pets/': item('get'), '/pets/{id}': item('get')})['findings'])

    def test_trailing_overlap_witness(self):
        result = self.inspect({'/{a}/me/': item('get'), '/books/{id}/': item('get')})
        self.assertEqual('/books/me/', result['findings'][0]['witness'])

    def test_all_emitted_witnesses_satisfy_both_routes(self):
        paths = {'/{a}/{b}': item('get'), '/books/{id}': item('get'), '/{entity}/me': item('get'),
                 '/books/mine': item('get'), '/{first}/{last}': item('post'), '/books/me/': item('get')}
        routes = list(paths)
        result = self.inspect(paths)
        self.assertGreater(len(result['findings']), 4)
        for finding in result['findings']:
            for index in finding['path_indices']:
                self.assertTrue(accepts(routes[index], finding['witness']), finding)

    def test_disjoint_literals_and_segment_counts(self):
        self.assertEqual([], self.inspect({'/a/{id}': item('get'), '/b/{id}': item('get'), '/a': item('get')})['findings'])

    def test_indices_ignore_extension_and_pairs_are_stable(self):
        result = self.inspect({'x-meta': {}, '/z': {}, '/{a}/me': item('get'), '/books/{id}': item('get')})
        self.assertEqual([1, 2], result['findings'][0]['path_indices'])
        self.assertEqual(2, result['findings'][0]['pair_index'])
        self.assertEqual(3, result['pairs_checked'])

    def test_unsupported_paths_fail_closed(self):
        for path in ['/a/{x}.json', '/a//b', '//', '/a%20b', '/a?q=x', '/a#x', '/caf\u00e9', '/a:b', 'pets', '/{}', '/{a/b}', '/{a b}']:
            with self.subTest(path=path):
                self.invalid(json.dumps(document({path: item('get')})).encode(), 'unsupported_path')

    def test_path_item_ref_rejected_even_with_operations(self):
        self.invalid(json.dumps(document({'/a': {'$ref': '#/secret', 'get': {}}})).encode(), 'unsupported_reference')

    def test_bad_containers_rejected(self):
        for data in [[], {}, {'openapi': '3.1.1', 'paths': []}, document({'/a': []}), document({'/a': {'get': None}})]:
            self.invalid(json.dumps(data).encode(), 'invalid_document')

    def test_versions_explicit(self):
        for version in ['3.0.0', '3.0.4', '3.1.0', '3.1.2']:
            self.assertEqual(0, tool.inspect_bytes(json.dumps({'openapi': version, 'paths': {}}).encode())['exit_code'])
        for version in ['3.2.1', '2.0', '3.1', '3.1.1-extra', None]:
            self.invalid(json.dumps({'openapi': version, 'paths': {}}).encode(), 'unsupported_version')

    def test_duplicate_json_keys_rejected_globally(self):
        self.invalid(b'{"openapi":"3.1.1","paths":{},"info":{"x":1,"x":2}}', 'invalid_json')

    def test_nonfinite_json_rejected(self):
        for token in ['NaN', 'Infinity', '-Infinity', '1e9999']:
            self.invalid(('{"openapi":"3.1.1","paths":{},"x":' + token + '}').encode(), 'invalid_json')

    def test_surrogates_rejected_in_values_and_keys(self):
        for data in [b'{"openapi":"3.1.1","paths":{},"x":"\uD800"}', b'{"openapi":"3.1.1","paths":{},"\uDFFF":0}']:
            self.invalid(data, 'invalid_json')

    def test_utf8_and_json_errors_neutral(self):
        for data in [b'\xff', b'{SECRET', b'openapi: 3.1.1', b'{} {}']:
            self.invalid(data, 'invalid_json')

    def test_byte_bound(self):
        self.invalid(b' ' * (tool.MAX_BYTES + 1), 'bounds_exceeded')

    def test_depth_bound(self):
        self.invalid(('{"openapi":"3.1.1","paths":{},"x":' + '[' * 66 + '0' + ']' * 66 + '}').encode(), 'bounds_exceeded')

    def test_node_bound(self):
        data = json.dumps(document({}, x=[0] * tool.MAX_NODES)).encode()
        self.invalid(data, 'bounds_exceeded')

    def test_path_bound(self):
        self.invalid(json.dumps(document({f'/p{i}': {} for i in range(501)})).encode(), 'bounds_exceeded')

    def test_segment_and_length_bounds(self):
        for path in ['/' + '/'.join(['x'] * 65), '/' + 'x' * 4096]:
            self.invalid(json.dumps(document({path: {}})).encode(), 'bounds_exceeded')

    def test_pair_bound_is_enforced(self):
        with patch.object(tool, 'MAX_PAIRS', 1):
            self.invalid(json.dumps(document({'/a': {}, '/b': {}, '/c': {}})).encode(), 'bounds_exceeded')

    def test_finding_bound_rejects_without_partial_report(self):
        with patch.object(tool, 'MAX_FINDINGS', 1):
            self.invalid(json.dumps(document({'/{a}/me': item('get', 'post'), '/books/{id}': item('get', 'post')})).encode(), 'bounds_exceeded')

    def test_maximum_path_and_segment_length_accepted(self):
        for path in ['/' + '/'.join(['x'] * 64), '/' + 'x' * 4095]:
            self.assertEqual(0, self.inspect({path: {}})['exit_code'])

    def test_nesting_scan_ignores_brackets_and_escaped_quotes_in_strings(self):
        self.assertEqual(0, self.inspect({}, summary='[' * 90 + '\\"' + '}' * 90)['exit_code'])

    def test_exhaustive_small_pair_intersections_against_independent_oracle(self):
        patterns = ['/' + '/'.join(p) for p in itertools.product(['a', 'b', '{id}'], repeat=2)]
        patterns += ['/', '/a', '/{id}', '/a/', '/{id}/']
        concrete = ['/' + '/'.join(p) for size in range(1, 3)
                    for p in itertools.product(['a', 'b', 'example', ''], repeat=size)]
        for a, b in itertools.combinations(patterns, 2):
            intersection_exists = any(accepts(a, w) and accepts(b, w) for w in concrete)
            findings = self.inspect({a: item('get'), b: item('get')})['findings']
            self.assertEqual(intersection_exists, bool(findings), (a, b))
            for finding in findings:
                self.assertTrue(accepts(a, finding['witness']) and accepts(b, finding['witness']))

    def test_privacy_only_literal_witness_is_disclosed(self):
        result = self.inspect({'/{SECRET_NAME}/private-literal': dict(item('get'), summary='PRIVATE_METADATA'),
                               '/books/{id}': dict(item('get'), servers=[{'url': 'PRIVATE_SERVER'}])},
                              security=[{'PRIVATE_AUTH': []}], example='PRIVATE_EXAMPLE')
        output = json.dumps(result)
        self.assertIn('/books/private-literal', output)
        for secret in ['SECRET_NAME', 'PRIVATE_METADATA', 'PRIVATE_SERVER', 'PRIVATE_AUTH', 'PRIVATE_EXAMPLE']:
            self.assertNotIn(secret, output)

    def test_broken_output_and_help_flush(self):
        class Broken(io.StringIO):
            def flush(self):
                raise BrokenPipeError('SECRET')
        for args in [['--help'], ['-']]:
            with patch('sys.stdout', Broken()), patch('sys.stdin', io.TextIOWrapper(io.BytesIO(b'{"openapi":"3.1.1","paths":{}}'))):
                self.assertEqual(2, tool.main(args))


class CLI(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.exists(), 'route CLI implementation is missing')

    def run_cli(self, args, data=None):
        return subprocess.run([sys.executable, SCRIPT.name, *args], input=data, cwd=ROOT,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)

    def test_cli_crossing_stdin(self):
        run = self.run_cli(['-'], json.dumps(document({'/{a}/me': item('get'), '/books/{id}': item('get')})).encode())
        self.assertEqual(1, run.returncode, run.stderr)
        self.assertEqual('/books/me', json.loads(run.stdout)['findings'][0]['witness'])
        self.assertEqual(b'', run.stderr)

    def test_cli_clean_fixture(self):
        run = self.run_cli(['fixtures/clean.json'])
        self.assertEqual(0, run.returncode, run.stderr)
        self.assertEqual([], json.loads(run.stdout)['findings'])

    def test_cli_io_errors_hide_paths(self):
        run = self.run_cli(['SECRET_MISSING_FILE'])
        self.assertEqual(2, run.returncode)
        self.assertNotIn(b'SECRET', run.stdout + run.stderr)
        self.assertEqual('io_error', json.loads(run.stdout)['error']['code'])

    def test_cli_invalid_args_hide_values(self):
        for args in [[], ['--SECRET'], ['a', 'PRIVATE']]:
            run = self.run_cli(args)
            self.assertEqual(2, run.returncode)
            self.assertNotIn(b'PRIVATE', run.stdout + run.stderr)
            self.assertNotIn(b'SECRET', run.stdout + run.stderr)
            self.assertEqual('invalid_arguments', json.loads(run.stdout)['error']['code'])

    def test_cli_invalid_json_neutral(self):
        run = self.run_cli(['-'], b'{"SECRET":NaN}')
        self.assertEqual(2, run.returncode)
        self.assertEqual({'error': {'code': 'invalid_json'}}, json.loads(run.stdout))
        self.assertEqual(b'', run.stderr)

    def test_cli_help(self):
        run = self.run_cli(['--help'])
        self.assertEqual(0, run.returncode)
        self.assertIn(b'Usage:', run.stdout)
        self.assertEqual(b'', run.stderr)


if __name__ == '__main__':
    unittest.main()
