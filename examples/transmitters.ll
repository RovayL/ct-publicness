declare i32 @callee_a(i32)
declare i32 @callee_b(i32)

define i32 @direct_const(i32 %x) {
entry:
  ret i32 42
}

define i32 @direct_identity(i32 %x) {
entry:
  %y = add i32 %x, 1
  ret i32 %y
}

define i32 @tx_div(i32 %a, i32 %b) {
entry:
  %q = sdiv i32 %a, %b
  %r = add i32 %q, 1
  ret i32 %r
}

define i32 @tx_rem(i32 %a, i32 %b) {
entry:
  %q = urem i32 %a, %b
  %r = add i32 %q, 1
  ret i32 %r
}

define ptr @tx_indirect_call_target(i1 %flag) {
entry:
  %chosen = select i1 %flag, ptr @callee_a, ptr @callee_b
  %res = call i32 %chosen(i32 7)
  ret ptr %chosen
}

define i32 @tx_direct_call_const(i32 %x) {
entry:
  %r = call i32 @direct_const(i32 %x)
  ret i32 %r
}

define i32 @tx_direct_call_identity(i32 %x) {
entry:
  %r = call i32 @direct_identity(i32 %x)
  ret i32 %r
}

define i32 @tx_atomicrmw_addr(ptr %base, i32 %idx, i32 %delta) {
entry:
  %addr = getelementptr i32, ptr %base, i32 %idx
  %old = atomicrmw add ptr %addr, i32 %delta seq_cst
  %sum = add i32 %old, 1
  ret i32 %sum
}

define i32 @tx_cmpxchg_extract(ptr %p, i32 %expected, i32 %desired) {
entry:
  %pair = cmpxchg ptr %p, i32 %expected, i32 %desired seq_cst seq_cst
  %old = extractvalue { i32, i1 } %pair, 0
  %ok = extractvalue { i32, i1 } %pair, 1
  %ok_i32 = zext i1 %ok to i32
  %sum = add i32 %old, %ok_i32
  ret i32 %sum
}

define i32 @tx_cmpxchg_insert_extract(ptr %p, i32 %expected, i32 %desired) {
entry:
  %pair = cmpxchg ptr %p, i32 %expected, i32 %desired seq_cst seq_cst
  %patched = insertvalue { i32, i1 } %pair, i1 true, 1
  %ok = extractvalue { i32, i1 } %patched, 1
  %ok_i32 = zext i1 %ok to i32
  ret i32 %ok_i32
}

define i32 @tx_atomicrmw_alias_eq(ptr %base) {
entry:
  %via_gep = getelementptr i32, ptr %base, i32 0
  %base_i = ptrtoint ptr %base to i64
  %base_i0 = add i64 %base_i, 0
  %via_cast = inttoptr i64 %base_i0 to ptr
  %old = atomicrmw add ptr %via_gep, i32 1 seq_cst
  %new = load i32, ptr %via_cast
  %same = icmp eq i32 %old, %new
  %same_i32 = zext i1 %same to i32
  ret i32 %same_i32
}
