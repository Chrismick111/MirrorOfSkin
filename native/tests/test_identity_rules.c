#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <string.h>
#include "sinners_native.c"

static void row(int index, unsigned sinner, const char *identity, double weight, const char *base) {
  g_rows[index].sinner = sinner;
  g_rows[index].enabled = 1;
  g_rows[index].weight = weight;
  strcpy(g_rows[index].identity, identity);
  strcpy(g_rows[index].asset_key, identity);
  strcpy(g_rows[index].appearance_name, identity);
  strcpy(g_rows[index].base_identity, base);
}

int main(void) {
  memset(g_rows, 0, sizeof(g_rows));
  g_rowCount = 3;
  row(0, 101, "10102", 1.0, "");
  row(1, 101, "10201", 1.0, "10110");
  row(2, 101, "10301", 1.0, "10111");

  Unit unit;
  memset(&unit, 0, sizeof(unit));
  unit.used = 1;
  unit.sinner = 101;
  strcpy(unit.baseName, "10110");

  rebuild_candidates(&unit);
  assert(unit.ncand == 1);
  assert(unit.cand[0] == 1);

  strcpy(unit.baseName, "10110_Yisang_DeadButterflyAppearance");
  rebuild_candidates(&unit);
  assert(unit.ncand == 1 && unit.cand[0] == 1);

  strcpy(unit.baseName, "10199");
  rebuild_candidates(&unit);
  assert(unit.ncand == 1 && unit.cand[0] == 0);

  memset(g_rows, 0, sizeof(g_rows));
  g_rowCount = 2;
  row(0, 101, "10102", 1.0, "");
  row(1, 101, "10201", 0.0, "10110");
  strcpy(unit.baseName, "10110");
  rebuild_candidates(&unit);
  assert(unit.ncand == 1 && unit.cand[0] == 0);

  puts("PASS per-identity rule selects only matching base and falls back to generic");
  return 0;
}
