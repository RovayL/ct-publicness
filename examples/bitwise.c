#include <stdint.h>

int bitwise_swap(int *a, int *b)
{
  int tmp = *a;
  *a = *a ^ *b;
  *b = *a ^ *b;
  *a = *a ^ *b;
  return tmp;
}

// return 1 if x == y, 0 otherwise
int bitwise_eq(int x, int y)
{
  uint32_t d = (uint32_t)(x ^ y);
  uint32_t mask = (d - 1) & ~d;
  return (int)(mask >> 31);
}

// Secret-dependent load address
int bitwise_secret_index(int *table, int secret, int mask)
{
  return table[secret & mask];
}

// Secret-dependent store
int bitwise_secret_store(int *table, int secret, int shift, int val)
{
  table[secret >> shift] = val;
  return val;
}
