#include <stdint.h>

#define ROTR32(x, n) (((x) >> (n)) | ((x) << (32 - (n))))

// Classic non-constant-time square-and-multiply exponentiation kernel.
uint32_t rsa_square_multiply(uint32_t base, uint32_t exp, uint32_t mod) {
  uint32_t acc = 1u % mod;
  while (exp != 0u) {
    if (exp & 1u) {
      acc = (acc * base) % mod;
    }
    base = (base * base) % mod;
    exp >>= 1;
  }
  return acc;
}

// Branchless ladder-style update for comparison with square-and-multiply.
uint32_t rsa_ladder_mix(uint32_t r0, uint32_t r1, uint32_t bit, uint32_t mod) {
  uint32_t prod = (r0 * r1) % mod;
  uint32_t sq0 = (r0 * r0) % mod;
  uint32_t sq1 = (r1 * r1) % mod;
  uint32_t mask = 0u - (bit & 1u);
  uint32_t new_r0 = (prod & mask) | (sq0 & ~mask);
  uint32_t new_r1 = (sq1 & mask) | (prod & ~mask);
  return new_r0 ^ new_r1;
}

// SHA-256 compression-round style kernel with dynamic message and constant loads.
uint32_t sha256_round_kernel(
  uint32_t a,
  uint32_t b,
  uint32_t c,
  uint32_t d,
  uint32_t e,
  uint32_t f,
  uint32_t g,
  uint32_t h,
  const uint32_t *w,
  const uint32_t *k,
  int round
) {
  uint32_t s1 = ROTR32(e, 6) ^ ROTR32(e, 11) ^ ROTR32(e, 25);
  uint32_t ch = (e & f) ^ ((~e) & g);
  uint32_t temp1 = h + s1 + ch + k[round] + w[round];
  uint32_t s0 = ROTR32(a, 2) ^ ROTR32(a, 13) ^ ROTR32(a, 22);
  uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
  uint32_t temp2 = s0 + maj;
  return temp1 + temp2 + d;
}

// Paillier-style lookup kernel with a direct table access.
uint32_t paillier_encrypt_lookup(
  const uint32_t *g_pows,
  uint32_t msg,
  uint32_t r_to_n,
  uint32_t n2
) {
  uint32_t gm = g_pows[msg & 7u];
  return (gm * r_to_n) % n2;
}

// Constant-time style Paillier lookup by scanning the whole table.
uint32_t paillier_encrypt_ct_lookup(
  const uint32_t *g_pows,
  uint32_t msg,
  uint32_t r_to_n,
  uint32_t n2
) {
  uint32_t gm = 0;
  uint32_t target = msg & 7u;
  for (uint32_t i = 0; i < 8; i++) {
    uint32_t d = i ^ target;
    uint32_t neg = ~d + 1u;
    uint32_t eq = ((d | neg) >> 31) ^ 1u;
    uint32_t mask = 0u - eq;
    gm |= g_pows[i] & mask;
  }
  return (gm * r_to_n) % n2;
}

// Constant-time memcmp style primitive used by many protocol stacks.
uint32_t ct_memcmp_u8(const uint8_t *lhs, const uint8_t *rhs, int n) {
  uint32_t diff = 0;
  for (int i = 0; i < n; i++) {
    diff |= (uint32_t)(lhs[i] ^ rhs[i]);
  }
  return diff;
}
