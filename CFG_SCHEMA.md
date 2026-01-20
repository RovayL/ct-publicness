NDJSON CFG/Path Schema (v0)

Each line is one JSON object. All records include:
- kind: "func_summary" | "block" | "edge" | "path" | "pp_coverage" | "path_summary"
- fn: function name (string)

Path condition formats
- Default: path_cond (string constraints)
- Optional: path_cond_json (structured JSON constraints)
- Toggle via -public-data-path-cond-format=string|json|both

path_cond_json operators
- "==" and "!=" with "lhs"/"rhs" strings
- "and" with "terms" array of nested expressions

Block records:
{
  "kind":"block",
  "fn":"foo",
  "bb":"bb0",
  "succs":["bb1","bb2"],
  "term_pp":"foo:bb0:i17",
  "term_op":"br",
  "cond":"v5",        // optional
  "target":"v9"       // optional (indirectbr)
}

Edge records:
{
  "kind":"edge",
  "fn":"foo",
  "from":"bb0",
  "to":"bb1",
  "term_pp":"foo:bb0:i17",
  "branch":"cond" | "uncond" | "switch" | "indirect",
  "cond":"v5",          // optional
  "sense":"true|false", // only for conditional branches
  "case":"const:i32:7", // only for switch cases
  "default":true,       // only for switch default
  "target":"v9"         // only for indirectbr
}

Path records:
{
  "kind":"path",
  "fn":"foo",
  "path_id":3,
  "bbs":["bb0","bb1","bb2"],
  "decisions":[
    {"pp":"foo:bb0:i17","kind":"br","succ":"bb1","cond":"v5","sense":"true"},
    {"pp":"foo:bb1:i4","kind":"switch","succ":"bb3","cond":"v7","case":"const:i32:7"},
    {"pp":"foo:bb1:i4","kind":"switch","succ":"bb4","cond":"v7","default":true},
    {"pp":"foo:bb2:i1","kind":"indirect","succ":"bb5","target":"v9"}
  ],
  "pp_seq":["foo:bb0:i0","foo:bb0:i1","foo:bb1:i0"],
  "path_cond_json":[
    {"op":"==","lhs":"v5","rhs":"const:i1:1"},
    {"op":"and","terms":[
      {"op":"!=","lhs":"v7","rhs":"const:i32:1"},
      {"op":"!=","lhs":"v7","rhs":"const:i32:2"}
    ]},
    {"op":"==","lhs":"v9","rhs":"label:bb5"}
  ],
  "path_cond":[
    "v5==const:i1:1",
    "v7==const:i32:7",
    "v7!=const:i32:1 && v7!=const:i32:2",
    "v9==label:bb5"
  ]
}

Program point coverage records (optional):
{
  "kind":"pp_coverage",
  "fn":"foo",
  "pp":"foo:bb1:i2",
  "path_count":4,
  "path_ids":[0,1,2,3],
  "truncated":true
}

Path summary records:
{"kind":"path_summary","fn":"foo","paths_emitted":4,"truncated":false,"max_paths":200,"max_depth":256,"max_loop_iters":0,"cutoff_depth":false,"cutoff_loop":false,"const_pruned_br":0,"const_pruned_switch":0,"const_pruned_indirect":0,"dfs_calls":10,"dfs_leaves":4,"dfs_prune_max_paths":0,"dfs_prune_max_depth":0,"dfs_prune_loop":0}
{"kind":"path_summary","fn":"foo","paths_emitted":0,"disabled":true,"max_paths":0,"max_depth":256,"max_loop_iters":0}
Function summary records:
{
  "kind":"func_summary",
  "fn":"foo",
  "inst_count":28,
  "bb_count":3,
  "tx_count":12,
  "trace_emitted":28,
  "trace_truncated":false,
  "trace_max_inst":0
}
