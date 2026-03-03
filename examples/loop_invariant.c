#include <stdint.h>

// First-iteration publicness should lift to later iterations:
// `pub` is computed inside the loop and does not feed any transmitter.
int loop_public_value(int n, int x) {
  int i = 0;
  int acc = 0;
  while (i < n) {
    int pub = x + 7;
    acc ^= pub;
    i++;
  }
  return acc;
}

// The address-producing expression used for the table lookup should remain
// non-public in our model because it directly feeds a load-address
// transmitter on every iteration.
int loop_nonpublic_addr(int n, int *table, int base) {
  int i = 0;
  int acc = 0;
  while (i < n) {
    int idx = base + i;
    acc += table[idx];
    i++;
  }
  return acc;
}
