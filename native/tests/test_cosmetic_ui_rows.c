#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include "data_paths.h"
static HINSTANCE g_self;
#include "cosmetic_ui_rows.h"
#include "cosmetic_skill_catalog.h"

#define PNG "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef.png"
#define SPECIAL_PNG "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210.png"

static void test_defense_subtypes(void){
    char manifest[] =
        "MOSUI1\nD\t41\tGUARD\n"
        "S\t41\tdefense\t0\tGuard\t\n"
        "S\t42\tdefense\t0\tEvade\t" PNG "\n"
        "S\t42\tdefense\t4\tImproved Evade\t\n"
        "S\t43\tdefense\t0\tCounter A\t\n"
        "S\t44\tdefense\t0\tCounter B\t\n"
        "D\t42\tEVADE\nD\t43\tCOUNTER\nD\t44\tCOUNTER\n";
    CosmeticUiManifest table;
    assert(cosmetic_ui_parse(manifest, sizeof(manifest) - 1, &table));
    CosmeticUiFields fields = cosmetic_ui_author_fields(&table, 1070404, 0, 1, 0, 4, 0, 0);
    assert(fields.text && !strcmp(fields.text, "Guard"));
    fields = cosmetic_ui_author_fields(&table, 1011504, 0, 1, 0, 4, 0, 41);
    assert(fields.text && !strcmp(fields.text, "Improved Evade") && fields.png);
    fields = cosmetic_ui_author_fields(&table, 1011504, 0, 1, 0, 0, 0, 0);
    assert(fields.text && !strcmp(fields.text, "Evade"));
    assert(!cosmetic_ui_author_fields(&table, 1031504, 0, 1, 0, 4, 0, 0).text);
    assert(!cosmetic_ui_author_fields(&table, 1011504, 0, 1, 1, 4, 0, 0).text);
    assert(!cosmetic_ui_author_fields(&table, 1011504, 0, 1, -1, 4, 0, 0).text);
    assert(!cosmetic_ui_author_fields(&table, 999999, 0, 1, 0, 4, 0, 0).text);
    fields = cosmetic_ui_author_fields(&table, 44, 0, 1, 1, 4, 0, 0);
    assert(fields.text && !strcmp(fields.text, "Counter B"));

    char mixed[] =
        "MOSUI1\nS\t41\tdefense\t0\tGuard\t\nD\t41\tGUARD\n"
        "S\t42\tdefense\t0\tUntyped\t\n";
    assert(cosmetic_ui_parse(mixed, sizeof(mixed) - 1, &table));
    assert(!cosmetic_ui_author_fields(&table, 1070404, 0, 1, 0, 4, 0, 0).text);
    char no_match[] = "MOSUI1\nS\t41\tdefense\t0\tGuard\t\nD\t41\tGUARD\n";
    assert(cosmetic_ui_parse(no_match, sizeof(no_match) - 1, &table));
    assert(!cosmetic_ui_author_fields(&table, 1011504, 0, 1, 0, 4, 0, 41).text);
    char attack[] = "MOSUI1\nS\t42\tattack1\t0\tAttack\t\nD\t42\tEVADE\n";
    assert(!cosmetic_ui_parse(attack, sizeof(attack) - 1, &table));
    char orphan[] = "MOSUI1\nD\t42\tEVADE\n";
    assert(!cosmetic_ui_parse(orphan, sizeof(orphan) - 1, &table));
    char duplicate[] = "MOSUI1\nS\t42\tdefense\t0\tEvade\t\nD\t42\tEVADE\nD\t42\tGUARD\n";
    assert(!cosmetic_ui_parse(duplicate, sizeof(duplicate) - 1, &table));

    char derived[] =
        "MOSUI1\nS\t41\tdefense\t0\tParry\t" PNG "\nD\t41\tCONDITIONAL\n"
        "S\t42\tdefense\t0\tEvade\t\nD\t42\tEVADE\n";
    assert(cosmetic_ui_parse(derived, sizeof(derived) - 1, &table));
    fields = cosmetic_ui_author_fields(&table, 1011504, 0, 1, 0, 4, 0, 41);
    assert(fields.text && !strcmp(fields.text, "Evade") && !fields.png);
    fields = cosmetic_ui_author_fields(&table, 41, 0, 1, 1, 4, 0, 0);
    assert(fields.text && !strcmp(fields.text, "Parry") && fields.png);
    char only_derived[] = "MOSUI1\nS\t41\tdefense\t0\tParry\t\nD\t41\tCONDITIONAL\n";
    assert(cosmetic_ui_parse(only_derived, sizeof(only_derived) - 1, &table));
    assert(!cosmetic_ui_author_fields(&table, 1011504, 0, 1, 0, 4, 0, 41).text);
    assert(!cosmetic_ui_author_fields(&table, 1011504, 0, 1, -1, 4, 0, 0).text);
}

static void test_conditional_defense_subtypes(void){
    /* Catalog IDs 108205, 113704 and 112605 are conditional guard, evade and counter. */
    char manifest[] =
        "MOSUI1\nS\t51\tdefense\t0\tRegular Guard\t\nD\t51\tGUARD\n"
        "S\t52\tdefense\t0\tTriggered Guard\t\nD\t52\tCONDITIONAL_GUARD\n"
        "S\t53\tdefense\t0\tTriggered Evade\t\nD\t53\tCONDITIONAL_EVADE\n"
        "S\t54\tdefense\t0\tTriggered Counter\t\nD\t54\tCONDITIONAL_COUNTER\n"
        "S\t55\tdefense\t0\tTriggered Unknown\t\nD\t55\tCONDITIONAL\n";
    CosmeticUiManifest table;
    assert(cosmetic_ui_parse(manifest, sizeof(manifest) - 1, &table));
    const int ids[] = {1070404, 108205, 113704, 112605};
    const char *names[] = {"Regular Guard", "Triggered Guard", "Triggered Evade", "Triggered Counter"};
    for (size_t i = 0; i < sizeof(ids) / sizeof(*ids); ++i) {
        CosmeticUiFields fields = cosmetic_ui_author_fields(&table, ids[i], 0, 1, i > 0, 4, 0, 0);
        assert(fields.text && !strcmp(fields.text, names[i]));
    }
    assert(!cosmetic_ui_author_fields(&table, 1011504, 0, 1, 0, 4, 0, 0).text);
    assert(!cosmetic_ui_author_fields(&table, 108205, 0, 1, -1, 4, 0, 0).text);
    CosmeticUiFields fields = cosmetic_ui_author_fields(&table, 55, 0, 1, 1, 4, 0, 0);
    assert(fields.text && !strcmp(fields.text, "Triggered Unknown"));

    /* 122806 is a named conditional evade counterpart of 113704 in the stock catalog. */
    char mapped[] =
        "MOSUI1\nS\t122806\tdefense\t0\tMapped Evade\t\nD\t122806\tCONDITIONAL\n"
        "S\t53\tdefense\t0\tTriggered Evade\t\nD\t53\tCONDITIONAL_EVADE\n"
        "S\t56\tdefense\t0\tOther Evade\t\nD\t56\tCONDITIONAL_EVADE\n";
    assert(cosmetic_ui_parse(mapped, sizeof(mapped) - 1, &table));
    assert(!cosmetic_ui_author_fields(&table, 113704, 0, 1, 1, 4, 0, 0).text);
    fields = cosmetic_ui_author_fields(&table, 113704, 0, 1, 1, 4, 0, 122806);
    assert(fields.text && !strcmp(fields.text, "Mapped Evade"));
    assert(!cosmetic_ui_author_fields(&table, 108205, 0, 1, 1, 4, 0, 122806).text);
    char ordinary[] =
        "MOSUI1\nS\t122806\tdefense\t0\tMapped Evade\t\nD\t122806\tEVADE\n";
    assert(cosmetic_ui_parse(ordinary, sizeof(ordinary) - 1, &table));
    assert(!cosmetic_ui_author_fields(&table, 113704, 0, 1, 1, 4, 0, 122806).text);
}

static void test_imported_tier_three_names(void){
    char locale_only[] =
        "MOSUI1\nT\t10315\n"
        "S\t1031503\tunknown\t3\tStrike Air\t\n"
        "S\t1031506\tunknown\t3\tExcalibur\t\n";
    CosmeticUiManifest table;
    assert(cosmetic_ui_parse(locale_only, sizeof(locale_only) - 1, &table));
    int ordinary = sr_cosmetic_stock_display_skill("10315", NULL, 1011503, 3, 0, 0);
    int conditional = sr_cosmetic_stock_display_skill("10315", NULL, 1011505, 3, 0, 1);
    assert(ordinary == 1031503 && conditional == 1031506);
    for (int level = 0; level <= 4; ++level) {
        CosmeticUiFields regular = cosmetic_ui_author_fields(&table, 1011503, 3, 0, 0, level, 0, ordinary);
        CosmeticUiFields special = cosmetic_ui_author_fields(&table, 1011505, 3, 0, 1, level, 0, conditional);
        if (level < 3) {
            assert(!regular.text && !special.text);
        } else {
            assert(regular.text && !strcmp(regular.text, "Strike Air"));
            assert(special.text && !strcmp(special.text, "Excalibur"));
        }
    }
}

int main(void){
    test_defense_subtypes();
    test_conditional_defense_subtypes();
    test_imported_tier_three_names();
    char manifest[] =
        "MOSUI1\nT\t10101\nA\t1288_lastknight_appearance\n"
        "S\t11\tattack1\t0\tBase\t" PNG "\n"
        "S\t11\tattack1\t4\tUpgraded\t\n"
        "S\t12\tdefense\t0\tGuard\t\n"
        "S\t13\tconditional\t0\tSpecial\t" SPECIAL_PNG "\n"
        "S\t14\tattack2\t0\tFirst\t\n"
        "S\t15\tattack2\t4\tSecond\t\n"
        "S\t16\tconditional\t0\tOther special\t\n"
        "S\t17\tattack3\t0\t\t" PNG "\n"
        "P\t" PNG "\nB\tCustomBuff\t" PNG "\n";
    CosmeticUiManifest table;
    assert(cosmetic_ui_parse(manifest, sizeof(manifest) - 1, &table));
    CosmeticUiFields fields = cosmetic_ui_author_fields(&table, 11, 4, 0, -1, 4, 0, 0);
    assert(fields.text && !strcmp(fields.text, "Upgraded"));
    assert(fields.png && !strcmp(fields.png, PNG));
    fields = cosmetic_ui_author_fields(&table, 999, 1, 0, 0, 3, 0, 0);
    assert(fields.text && !strcmp(fields.text, "Base"));
    assert(!cosmetic_ui_author_fields(&table, 999, 1, 0, 1, 3, 0, 0).text);
    assert(!cosmetic_ui_author_fields(&table, 999, 1, 0, -1, 3, 0, 0).text);
    assert(!cosmetic_ui_author_fields(&table, 999, 2, 0, 0, 4, 0, 0).text);
    assert(!cosmetic_ui_author_fields(&table, 11, 1, 1, 0, 4, 0, 0).png);
    fields = cosmetic_ui_author_fields(&table, 999, 1, 1, 0, 4, 0, 0);
    assert(fields.text && !strcmp(fields.text, "Guard"));
    assert(!fields.png);
    assert(cosmetic_ui_author_fields(&table, 999, 1, 1, -1, 4, 0, 0).text);
    assert(cosmetic_ui_author_fields(&table, 12, 0, 1, -1, 4, 0, 0).text);
    assert(cosmetic_ui_author_fields(&table, 12, 0, -1, -1, 4, 0, 0).text);
    assert(cosmetic_ui_author_fields(&table, 11, 0, -1, -1, 4, 0, 0).text);
    assert(!cosmetic_ui_author_fields(&table, 999, 1, -1, 0, 4, 0, 0).text);
    assert(cosmetic_ui_author_fields(&table, 13, 1, 0, 1, 0, 0, 0).text);
    ImportedAttackRoute routes[] = {{999, 1, 3, 7, 0}, {11, 1, 3, 7, 0}, {13, 1, 3, 7, 0}, {16, 1, 3, 7, 0}};
    assert(cosmetic_ui_route_id(&table, routes, 3, 999, 1, 3, 7, 1) == 13);
    assert(cosmetic_ui_route_id(&table, routes, 2, 999, 1, 3, 7, 1) == 0);
    assert(cosmetic_ui_route_id(&table, routes + 1, 2, 999, 1, 3, 7, 1) == 0);
    assert(cosmetic_ui_route_id(&table, routes, 3, 999, 1, 2, 7, 1) == 13);
    assert(cosmetic_ui_route_id(&table, routes, 3, 999, 1, 3, 7, -1) == 0);
    assert(cosmetic_ui_route_id(&table, routes, 4, 999, 1, 3, 7, 1) == 0);
    assert(cosmetic_ui_routed_tier(0, 1, 1) == 1);
    assert(!cosmetic_ui_routed_tier(0, 1, 0));
    assert(!cosmetic_ui_routed_tier(0, 1, -1));
    assert(!cosmetic_ui_routed_tier(2, 1, 1));
    assert(!cosmetic_ui_routed_tier(0, 0, 1));
    fields = cosmetic_ui_author_fields(&table, 999, 1, 1, 0, 4, 0, 12);
    assert(fields.text && !strcmp(fields.text, "Guard") && !fields.png);
    fields = cosmetic_ui_author_fields(&table, 999, 3, 0, 0, 4, 0, 17);
    assert(!fields.text && fields.png && !strcmp(fields.png, PNG));
    fields = cosmetic_ui_author_fields(&table, 11, 1, 0, -1, 4, 0, 0);
    assert(fields.text && !strcmp(fields.text, "Upgraded") && fields.png);
    fields = cosmetic_ui_author_fields(&table, 999, 0, 0, 1, 4, 13, 0);
    assert(fields.text && !strcmp(fields.text, "Special") && !strcmp(fields.png, SPECIAL_PNG));
    ImportedAttackRoute different_coins[] = {{999, 1, 2, 7, 0}, {13, 1, 4, 7, 0}};
    for (int coins = 0; coins <= 5; ++coins) {
        int routed = cosmetic_ui_route_id(&table, different_coins, 2, 999, 1, coins, 7, 1);
        assert(routed == 13);
        fields = cosmetic_ui_author_fields(&table, 999, 0, 0, 1, 4, routed, 0);
        assert(fields.text && !strcmp(fields.text, "Special"));
        assert(fields.png && !strcmp(fields.png, SPECIAL_PNG));
    }
    assert(!cosmetic_ui_route_id(&table, different_coins, 2, 998, 1, 2, 7, 1));
    assert(!cosmetic_ui_route_id(&table, different_coins, 2, 999, 1, 2, 7, 0));
    routes[3].coins = 4;
    assert(cosmetic_ui_route_id(&table, routes, 4, 999, 1, 3, 7, 1) == 13);
    assert(!cosmetic_ui_route_id(&table, routes, 4, 999, 1, 0, 7, 1));
    assert(!cosmetic_ui_author_fields(&table, 999, 0, 0, 1, 4, 0, 0).png);
    CosmeticUiManifest unique = table;
    unique.skills[6].role = COSMETIC_UI_UNKNOWN;
    fields = cosmetic_ui_author_fields(&unique, 999, 0, 0, 1, 4, 0, 0);
    assert(!strcmp(fields.text, "Special") && !strcmp(fields.png, SPECIAL_PNG));
    fields = cosmetic_ui_author_fields(&unique, 11, 1, 0, 1, 4, 0, 0);
    assert(!strcmp(fields.text, "Special") && !strcmp(fields.png, SPECIAL_PNG));
    fields = cosmetic_ui_author_fields(&unique, 13, 1, 0, 0, 3, 0, 0);
    assert(!strcmp(fields.text, "Base") && !strcmp(fields.png, PNG));
    assert(table.target == 10101 && table.portrait &&
           table.appearance && !strcmp(table.appearance, "1288_lastknight_appearance"));
    assert(cosmetic_ui_status(&table, "CustomBuff"));
    assert(!cosmetic_ui_status(&table, "custombuff"));
    char bad[] = "MOSUI1\nP\t../../a.png\n";
    assert(!cosmetic_ui_parse(bad, sizeof(bad) - 1, &table));
    char reverted[] = "MOSUI1\nS\t11\tattack1\t0\tAuthored\t" PNG "\n"
                      "R\t11\tattack1\t3\t\t\nS\t11\tattack1\t4\tNew name\t\n";
    assert(cosmetic_ui_parse(reverted, sizeof(reverted) - 1, &table));
    fields = cosmetic_ui_author_fields(&table, 11, 1, 0, 0, 2, 0, 0);
    assert(fields.text && !strcmp(fields.text, "Authored") && fields.png);
    fields = cosmetic_ui_author_fields(&table, 11, 1, 0, 0, 3, 0, 0);
    assert(!fields.text && fields.png && !strcmp(fields.png, PNG));
    fields = cosmetic_ui_author_fields(&table, 11, 1, 0, 0, 4, 0, 0);
    assert(fields.text && !strcmp(fields.text, "New name") && fields.png);
    char conflicting[] = "MOSUI1\nR\t11\tattack1\t3\tUnexpected name\t\n";
    assert(!cosmetic_ui_parse(conflicting, sizeof(conflicting) - 1, &table));
    char no_appearance[] = "MOSUI1\nT\t10101\n";
    assert(cosmetic_ui_parse(no_appearance, sizeof(no_appearance) - 1, &table) && !table.appearance);
    char repeated[] = "MOSUI1\nA\tOld\nA\tNew\n";
    assert(!cosmetic_ui_parse(repeated, sizeof(repeated) - 1, &table));
    char invalid_appearance[] = "MOSUI1\nA\t../1288_lastknight_appearance\n";
    assert(!cosmetic_ui_parse(invalid_appearance, sizeof(invalid_appearance) - 1, &table));
    char locale_defense[] =
        "MOSUI1\nS\t999999\tunknown\t0\tExact private defense\t" PNG "\n"
        "S\t33\tdefense\t0\tGeneric defense\t\n";
    assert(cosmetic_ui_parse(locale_defense, sizeof(locale_defense) - 1, &table));
    fields = cosmetic_ui_author_fields(&table, 999999, 0, 1, 0, 4, 0, 0);
    assert(fields.text && !strcmp(fields.text, "Exact private defense") && fields.png);
    return 0;
}
