# openapi-route-witness

[![tests](https://github.com/maomao-1937/openapi-route-witness/actions/workflows/tests.yml/badge.svg)](https://github.com/maomao-1937/openapi-route-witness/actions/workflows/tests.yml)

Produce a concrete intersection witness for a small, explicit subset of JSON
OpenAPI 3.0.x / 3.1.x route patterns. For `/{entity}/me` and `/books/{id}`
sharing `get`, the witness is `/books/me`. Exit codes make it usable in a local
check or CI step. Python 3.11+; standard library only; no network access.

## Install and run from source

Download this repository or clone it, enter its directory, then run:

```console
python openapi_route_witness.py fixtures/crossing.json
python openapi_route_witness.py fixtures/precedence.json
python openapi_route_witness.py --help
python -m unittest discover -s tests -v
```

There is no package installation, dependency file, configuration file, environment
variable, API key, or service. All limits are fixed in the script. Standard Python
UTF-8 file input works on Windows, macOS, and Linux; tests have been run on
Windows with Python 3.11. Stdin is selected by a single `-` argument:

```console
python openapi_route_witness.py - < fixtures/crossing.json
```

The redirection example uses a POSIX shell or Windows cmd. In PowerShell:

```powershell
Get-Content -Raw -Encoding UTF8 fixtures/crossing.json | python openapi_route_witness.py -
```

Input is one UTF-8 JSON object containing `openapi` and a `paths` object. Minimal
profile input (this checker does not validate all required OpenAPI fields):

```json
{"openapi":"3.1.1","paths":{"/{entity}/me":{"get":{}},"/books/{id}":{"get":{}}}}
```

Example output, formatted here for reading:

```json
{
  "profile": "ascii-segment-v1",
  "path_count": 2,
  "pairs_checked": 1,
  "findings": [{
    "code": "crossing_overlap",
    "severity": "error",
    "path_indices": [0, 1],
    "pair_index": 0,
    "method": "get",
    "witness": "/books/me"
  }],
  "exit_code": 1
}
```

Output is one compact JSON line on stdout; handled errors have a neutral shape,
for example `{"error":{"code":"unsupported_reference"}}`. No source filename,
exception message, offending argument, or invalid value is echoed. Help prints
static text. Broken output, including a failed help flush, returns 2.

## Matching and interpretation

- Literal segments use only ASCII `A-Z a-z 0-9 . _ ~ -`. A template occupies a
  whole segment, such as `{petId}`; names use that same nonempty character set.
  Each template independently accepts a nonempty segment. Names are labels;
  repeated names do not impose equality constraints in this model.
- `/` is supported. A single trailing slash is significant: `/pets`, `/pets/`,
  and `/pets/{id}` are distinct, and an empty trailing segment cannot satisfy a
  template. Consecutive empty segments such as `/a//b` and `//` are rejected.
- Mixed segments (`{id}.json`), percent encoding, non-ASCII literals, queries,
  fragments, spaces, and other reserved characters are unsupported (exit 2).
  There is no decoding, case folding, dot-segment resolution, or normalization.
- Only lowercase `get`, `put`, `post`, `delete`, `options`, `head`, `patch`, and
  `trace` fields declare operations; each present operation must be an object.
  There is no implicit HEAD for GET, OPTIONS synthesis, or method inheritance.
  Other Path Item metadata/unknown fields and `x-` extensions are ignored.
  Paths-level `x-` entries are excluded from route indices. A Path Item `$ref`
  is rejected even when sibling operations exist; no route is silently skipped.
- A pair intersects only if segment counts match, literals agree at every
  jointly literal position, and no template meets an empty segment. The witness
  uses a constrained literal where available and `example` for two templates.
- `equivalent_template` is an error for identical normalized templates with
  different names, globally, even with different or absent methods. It has
  `method: null` because this is a Paths-level finding.
- `crossing_overlap` is an error for each shared declared method when each
  pattern adds a literal restriction at a different position. This is a
  portability policy for potentially ambiguous resolution.
- `specific_precedence` is informational when one pattern's literal restrictions
  contain the other's. `preferred_path_index` identifies that pattern. Concrete
  precedence follows the specification; extending the policy to partially
  templated dominance is an explicit model choice, not a guarantee about a router.

Indices are zero-based, in JSON input order after omitting Paths extensions.
`pair_index` enumerates **all** unordered path pairs `(0,1), (0,2), ...`, including
disjoint pairs. Findings follow pair order, then the method order listed above.

| Exit | Meaning |
| --- | --- |
| 0 | No error findings; informational precedence may be present |
| 1 | Equivalent templates or same-method crossing overlaps |
| 2 | Invalid/unsupported input, exceeded bounds, input/output failure |

Neutral error codes are `invalid_arguments`, `io_error`, `invalid_json`,
`invalid_document`, `unsupported_version`, `unsupported_path`,
`unsupported_reference`, and `bounds_exceeded`. Output failures may prevent any
report. An exit-2 input produces no partial route findings.

## Boundaries and privacy

**Witnesses intentionally disclose input path literal segments.** A route literal
can itself be sensitive. Review stdout before sharing it. Parameter names, API
metadata, server URLs, authentication fields, example values, and source paths
are never included. No telemetry or network calls are made.

| Bound | Maximum |
| --- | ---: |
| Input bytes | 1,048,576 |
| Tree depth (root is 1, includes keys and scalar values) | 64 |
| Tree nodes (keys, values, containers count separately) | 100,000 |
| Paths (excluding Paths-level extensions) | 500 |
| Unordered pairs | 124,750 |
| Segments per path (including a trailing empty segment) | 64 |
| Characters per path | 4,096 |
| Emitted findings | 10,000 |

The nesting scan runs before JSON decoding; all metadata contributes to generic
input bounds. Duplicate JSON keys anywhere, nonfinite numbers (including overflow
such as `1e9999`), invalid UTF-8, and lone Unicode surrogates are rejected.
Pair scanning takes O(paths² × segments); the findings cap bounds report growth.

This is a bounded structural checker, **not a full OpenAPI validator or runtime
router emulator**. It does not read YAML, resolve references, interpret parameter
schemas/enums/serialization, inspect operation IDs, compose server URLs, traverse
callbacks/webhooks, or test a server. Route witnesses are structural examples;
they may violate an API's parameter constraints. OpenAPI 3.2.1 exists but 3.2.x
and Swagger/OpenAPI 2.x are explicitly unsupported here. Use a broader validator
alongside this tool. Research and alternatives: [RESEARCH.md](RESEARCH.md).

## 中文说明

这是一个 Python 3.11+ 标准库小工具，用具体路径展示 JSON OpenAPI 3.0.x / 3.1.x
路由模式的交集。例如 `/{entity}/me` 与 `/books/{id}` 同时声明 `get`，输出
`/books/me`。下载源码后直接执行上面的命令，无需安装依赖、配置环境变量或密钥。

退出码：`0` 表示无错误发现（可能包含优先级提示），`1` 表示等价模板或同方法交叉
重叠，`2` 表示输入无效、不支持、超限或读写失败。等价模板不依赖 HTTP 方法；普通
交叉仅比较共同声明的方法。更具体的模式按本工具规则报告为信息，不代表实际框架
一定以此路由。索引从零开始，按输入顺序定位；完整输出格式和限制见上表。

仅支持完整的 `{参数名}` 段和 ASCII 非保留字符字面段。根路径和末尾斜杠保留原意；
末尾空段不能匹配非空参数。百分号编码、混合模板段、连续空段、查询、片段、非 ASCII
字面字符均拒绝。Path Item `$ref` 不会被静默略过，而是返回 `2`。

**隐私例外：输出的 witness 会包含输入路径的字面段，分享前请检查。** 元数据、参数
名称、服务地址、认证字段、示例值和源文件路径不会输出。工具无网络请求。它不验证
完整规范，也不理解参数约束、YAML、引用、运行时路由或服务器 URL；OpenAPI 3.2.x
（包括已发布的 3.2.1）及 2.x 不在支持范围。合成夹具含合理的参数声明，但工具不做
Parameter Object 的完整校验。测试命令为 `python -m unittest discover -s tests -v`。

MIT License, copyright 2026 maomao-1937.
