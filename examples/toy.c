#include <stdint.h>

int foo(int *p, int secret, int x) {
  int y = x + 1;
  int z = *p;          // load address transmitter
  if (secret & 1) {    // branch condition transmitter
    y = y + z;
  }
  *p = y;              // store address transmitter
  return y;
}
