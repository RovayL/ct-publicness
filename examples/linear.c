#include <stdint.h>

int linear_arith(int a, int b) {
  int x = a + 3;
  int y = b ^ 0x5a;
  int z = x * y;
  return z - 7;
}

int linear_mem(int *p, int *q) {
  int x = *p;
  int y = *q;
  int z = x + y;
  *p = z;
  *q = x - y;
  return z;
}

int linear_ptrcmp(int *p) {
  int *z = 0;
  return p == z;
}
