#include <stdint.h>

// Quicksort partition kernel: branchy swaps plus load/store transmitters.
int quicksort_partition_kernel(int *arr, int low, int high) {
  int pivot = arr[high];
  int i = low - 1;
  for (int j = low; j < high; j++) {
    if (arr[j] < pivot) {
      i++;
      int tmp = arr[i];
      arr[i] = arr[j];
      arr[j] = tmp;
    }
  }
  int tmp = arr[i + 1];
  arr[i + 1] = arr[high];
  arr[high] = tmp;
  return i + 1;
}

// Travelling-salesman nearest-neighbor step over a dense distance matrix.
int tsp_choose_next_city(const int *dist, int city_count, int cur_city, uint32_t visited_mask) {
  int best_city = -1;
  int best_cost = 0x7fffffff;
  for (int city = 0; city < city_count; city++) {
    uint32_t seen = (visited_mask >> city) & 1u;
    int idx = cur_city * city_count + city;
    int cost = dist[idx];
    if (!seen && cost < best_cost) {
      best_cost = cost;
      best_city = city;
    }
  }
  return best_city;
}

// Jarvis-march style convex-hull step: choose the most counter-clockwise point.
int convex_hull_next_point(const int *xs, const int *ys, int n, int p) {
  int q = (p + 1) % n;
  for (int r = 0; r < n; r++) {
    int dx1 = xs[r] - xs[p];
    int dy1 = ys[r] - ys[p];
    int dx2 = xs[q] - xs[p];
    int dy2 = ys[q] - ys[p];
    int cross = dx1 * dy2 - dy1 * dx2;
    if (cross > 0) {
      q = r;
    }
  }
  return q;
}

// Recursive benchmark with a secret-dependent branch and a recursive call result.
int recursive_binary_search(const int *arr, int lo, int hi, int key) {
  if (lo > hi) {
    return -1;
  }
  int mid = lo + ((hi - lo) >> 1);
  int val = arr[mid];
  if (val == key) {
    return mid;
  }
  if (val < key) {
    return recursive_binary_search(arr, mid + 1, hi, key);
  }
  return recursive_binary_search(arr, lo, mid - 1, key);
}
