#include <stdint.h>

int loop_sum(int n, int *p) {
  int i = 0;
  int sum = 0;
  while (i < n) {
    sum += p[i];
    i++;
  }
  return sum;
}

int loop_branch(int n, int secret) {
  int i = 0;
  int x = 0;
  while (i < n) {
    if (secret & 1) {
      x += i;
    } else {
      x -= i;
    }
    i++;
  }
  return x;
}
