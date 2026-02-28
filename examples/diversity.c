#include <stdint.h>

// Constant-time style: branchless value selection.
int ct_branchless_select(int x, int y, int secret) {
  int bit = secret & 1;
  int mask = -bit;
  return (x & ~mask) | (y & mask);
}

// Intentionally non-constant-time: secret-dependent branch and memory access.
int nct_secret_branch_index(int *table, int secret, int idx) {
  if (secret & 1) {
    return table[idx];
  }
  return table[idx + 1];
}
