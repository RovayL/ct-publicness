; Explicit constant-condition IR microbenchmarks to exercise
; const_pruned_br / const_pruned_switch counters in PublicDataPass.

define i32 @const_pruned_br(i32 %x) {
entry:
  br i1 true, label %then, label %else

then:
  %a = add i32 %x, 1
  br label %merge

else:
  %b = add i32 %x, 2
  br label %merge

merge:
  %r = phi i32 [ %a, %then ], [ %b, %else ]
  ret i32 %r
}

define i32 @const_pruned_switch(i32 %x) {
entry:
  switch i32 3, label %default [
    i32 1, label %case1
    i32 3, label %case3
  ]

case1:
  %v1 = add i32 %x, 10
  br label %merge

case3:
  %v3 = add i32 %x, 30
  br label %merge

default:
  %vd = add i32 %x, 90
  br label %merge

merge:
  %r = phi i32 [ %v1, %case1 ], [ %v3, %case3 ], [ %vd, %default ]
  ret i32 %r
}
