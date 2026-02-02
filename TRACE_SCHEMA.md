NDJSON Trace Schema (v0)

Each line is one JSON object (one instruction).

Fields:
- fn: function name (string)
- bb: basic block label (string, stable per function)
- pp: program point "fn:bb:i<index>" (string)
- op: LLVM opcode name (string)
- def: SSA value id (string) or null if void-typed instruction
- uses: array of operand ids (strings). For PHI, operands are emitted as
  value/block pairs, where block entries use the basic block label string
  (same labels as CFG records).
- tx: optional transmitter object with:
  - kind: transmitter kind (string)
  - which: LLVM operand index for the transmitter (int)
- def_ty: optional LLVM type string for def
- use_tys: optional LLVM type strings for uses (parallel to uses list)
- icmp_pred: optional predicate string for ICmpInst (e.g., "eq", "slt")
- fcmp_pred: optional predicate string for FCmpInst (e.g., "oeq", "ult")

Trace index (optional)
If -public-data-trace-index is provided, an index NDJSON file is produced:
{"kind":"trace_index","fn":"foo","bb":"bb0","pp":"foo:bb0:i3","op":"add","def":"v7","line":42}

SSA value ids:
- arg<N> for unnamed arguments
- const:i<width>:<value> for integer constants
- const:fp:<value> for floating-point constants
- const:null / const:undef / const:poison for special constants
- const:<printed> for other constant kinds (e.g., aggregates/exprs)
- v<N> for generated ids
