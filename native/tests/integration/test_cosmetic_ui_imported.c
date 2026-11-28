/* Pass the published Myo, Lemuen, Purple Tear, Saber and any portrait-only MOSUI1 paths. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdio.h>
#include <wchar.h>
#include "data_paths.h"
static HINSTANCE g_self;
#include "cosmetic_ui_rows.h"
#include "cosmetic_skill_catalog.h"

typedef struct {
    char bytes[COSMETIC_UI_MAX_BYTES];
    CosmeticUiManifest table;
} ImportedAppearance;

static void load_appearance(const wchar_t *path, int target, ImportedAppearance *result){
    FILE *file = _wfopen(path, L"rb");
    assert(file);
    size_t size = fread(result->bytes, 1, sizeof(result->bytes), file);
    assert(feof(file) && !ferror(file));
    fclose(file);
    assert(cosmetic_ui_parse(result->bytes, size, &result->table));
    assert(!target || result->table.target == target);
}

static void check(const ImportedAppearance *appearance, int id, int tier, int defense,
                  int conditional, int level, const char *name, int icon){
    int mapped = 0;
    if (appearance) {
        const CosmeticUiManifest *table = &appearance->table;
        char target[16];
        snprintf(target, sizeof(target), "%d", table->target);
        const SrUiSkill *source = sr_ui_skill(id);
        if (source) {
            if (source->conditional == 1 || conditional < 0) conditional = source->conditional;
            if (defense < 0) defense = source->defense != 0;
            if (!tier && source->tier >= 1 && source->tier <= 3) tier = source->tier;
        }
        if (defense >= 0)
            mapped = sr_cosmetic_stock_display_skill(target, sr_ui_appearance_key(table->appearance),
                                                     id, tier, defense, conditional);
    }
    CosmeticUiFields fields = appearance ?
        cosmetic_ui_author_fields(&appearance->table, id, tier, defense, conditional, level, 0, mapped) :
        (CosmeticUiFields){0};
    assert((!name && !fields.text) || (name && fields.text && !strcmp(fields.text, name)));
    assert((fields.png != NULL) == icon);
    printf("target=%d skill=%d level=%d text=%s icon=%d\n",
           appearance ? appearance->table.target : 0, id, level,
           fields.text ? fields.text : "(stock)", icon);
}

int wmain(int argc, wchar_t **argv){
    int typed = argc == 7 && !wcscmp(argv[6], L"--typed-defense");
    if (argc != 6 && !typed) {
        fputs("Usage: test_cosmetic_ui_imported MYO_TSV LEMUEN_TSV PURPLE_TEAR_TSV SABER_TSV PORTRAIT_ONLY_TSV [--typed-defense]\n",
              stderr);
        return 2;
    }
    setbuf(stdout, NULL);
    static ImportedAppearance myo, lemuen, purple, saber, portrait_only;
    load_appearance(argv[1], 30902, &myo);
    load_appearance(argv[2], 11448, &lemuen);
    load_appearance(argv[3], 1048118, &purple);
    load_appearance(argv[4], 10315, &saber);
    load_appearance(argv[5], 0, &portrait_only);
    assert(portrait_only.table.portrait && !portrait_only.table.skill_count);

    check(&myo, 1070401, 0, -1, -1, 4, "Graze the Grass", 1);
    check(&myo, 1070402, 0, -1, -1, 4, "Quick Suppression", 1);
    check(&myo, 1070403, 0, -1, -1, 4, "Rapid Assault", 1);
    check(&myo, 1070404, 0, -1, -1, 4, typed ? NULL : "Adept Evasion", !typed);
    check(&myo, 1070304, 0, -1, -1, 4, "Adept Evasion", 1);
    check(&myo, 3090206, 0, 0, 1, 4, "Pinpoint Shot", 0);
    check(&myo, 1011505, 0, -1, -1, 4, NULL, 0);

    check(&lemuen, 1011503, 0, -1, -1, 4, "Salutatio Sclopeti: Memento Mor", 1);
    check(&lemuen, 1011504, 0, -1, -1, 4, "Manoeuvre", 1);
    check(&lemuen, 1011505, 0, -1, -1, 4, NULL, 0);
    check(&lemuen, 1144801, 1, 0, 0, 1, "Salvē Etiam", 1);

    check(&purple, 1011503, 0, -1, -1, 4, "Violet Blade", 1);
    check(&purple, 1011504, 0, -1, -1, 4, NULL, 0);
    check(&purple, 1011505, 0, -1, -1, 4, NULL, 0);
    check(&purple, 104811899, 0, 0, 1, 4, "Mirage Storm", 1);
    check(&purple, 104811894, 0, 1, 0, 4, "Myriad Arts: Guard", 0);

    check(&saber, 1011503, 0, -1, -1, 2, NULL, 0);
    check(&saber, 1011503, 0, -1, -1, 3, "Strike Air（风王铁锤）", 0);
    check(&saber, 1011505, 0, -1, -1, 3, "Excalibur（誓约胜利之剑）", 0);
    check(&saber, 1011505, 0, -1, -1, 4, "Excalibur（誓约胜利之剑）", 0);
    check(&lemuen, 1011503, 0, -1, -1, 4, "Salutatio Sclopeti: Memento Mor", 1);
    check(&portrait_only, 1011503, 0, -1, -1, 4, NULL, 0);
    check(&portrait_only, 1011504, 0, -1, -1, 4, NULL, 0);
    check(&portrait_only, 1011505, 0, -1, -1, 4, NULL, 0);
    check(NULL, 1011503, 0, -1, -1, 4, NULL, 0);
    return 0;
}
