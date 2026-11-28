#ifndef SR_COSMETIC_UI_ROWS_H
#define SR_COSMETIC_UI_ROWS_H
#include <limits.h>
#include <stddef.h>
#include <string.h>
#include "imported_skin.h"
#include "cosmetic_skill_catalog.h"

enum { COSMETIC_UI_MAX_ROWS = 512, COSMETIC_UI_MAX_BYTES = 256 * 1024 };
enum { COSMETIC_UI_UNKNOWN, COSMETIC_UI_ATTACK1, COSMETIC_UI_ATTACK2,
       COSMETIC_UI_ATTACK3, COSMETIC_UI_DEFENSE, COSMETIC_UI_CONDITIONAL };
enum { COSMETIC_UI_DERIVED_DEFENSE = 4 }; /* Stock defense types occupy 1 to 3. */
typedef struct { const char *text, *png; } CosmeticUiFields;
typedef struct { int id, role, level; CosmeticUiFields art; int restore_name, defense_type; } CosmeticUiSkill;
typedef struct { const char *key, *png; } CosmeticUiStatus;
typedef struct { int id, type; } CosmeticUiDefense;
typedef struct {
    CosmeticUiSkill skills[COSMETIC_UI_MAX_ROWS];
    CosmeticUiStatus statuses[COSMETIC_UI_MAX_ROWS];
    size_t skill_count, status_count;
    int target;
    const char *portrait, *appearance;
} CosmeticUiManifest;

static int cosmetic_ui_png_name(const char *name){
    return strlen(name) == 68 && !strcmp(name + 64, ".png") &&
           strspn(name, "0123456789abcdef") == 64;
}

static int cosmetic_ui_number(const char *s, int *result){
    if (!*s) return 0;
    int value = 0;
    for (; *s; ++s) {
        if (*s < '0' || *s > '9' || value > (INT_MAX - (*s - '0')) / 10) return 0;
        value = value * 10 + (*s - '0');
    }
    *result = value;
    return 1;
}

/* Strings borrow the caller's validated UTF-8 buffer. */
static int cosmetic_ui_parse(char *data, size_t length, CosmeticUiManifest *out){
    static const char *const roles[] = {"unknown", "attack1", "attack2", "attack3", "defense", "conditional"};
    static const char *const defense_types[] = {
        "", "GUARD", "EVADE", "COUNTER", "CONDITIONAL",
        "CONDITIONAL_GUARD", "CONDITIONAL_EVADE", "CONDITIONAL_COUNTER"
    };
    const size_t header = sizeof("MOSUI1\n") - 1;
    memset(out, 0, sizeof(*out));
    if (length < header || length > COSMETIC_UI_MAX_BYTES || memchr(data, 0, length) ||
        memcmp(data, "MOSUI1\n", header) || data[length - 1] != '\n') return 0;
    size_t rows = 0;
    CosmeticUiDefense defenses[COSMETIC_UI_MAX_ROWS];
    size_t defense_count = 0;
    for (char *line = data + header; line < data + length;) {
        char *next = memchr(line, '\n', (size_t)(data + length - line));
        if (!next || ++rows > COSMETIC_UI_MAX_ROWS) return 0;
        *next++ = 0;
        char *cell[6] = {line};
        size_t cells = 1;
        for (char *p = line; *p; ++p) {
            if (*p == '\t' && cells < 6) {
                *p = 0;
                cell[cells++] = p + 1;
            } else if ((unsigned char)*p < 32 || *p == 127) return 0;
        }
        if (cells == 6 && (!strcmp(cell[0], "S") || !strcmp(cell[0], "R"))) {
            CosmeticUiSkill row = {0};
            row.restore_name = cell[0][0] == 'R';
            while (row.role < 6 && strcmp(cell[2], roles[row.role])) row.role++;
            if (row.role >= 6 || !cosmetic_ui_number(cell[1], &row.id) || !row.id ||
                !cosmetic_ui_number(cell[3], &row.level) ||
                (row.restore_name && *cell[4]) || (*cell[5] && !cosmetic_ui_png_name(cell[5]))) return 0;
            row.art.text = *cell[4] ? cell[4] : NULL;
            row.art.png = *cell[5] ? cell[5] : NULL;
            for (size_t i = 0; i < out->skill_count; ++i) {
                const CosmeticUiSkill *other = &out->skills[i];
                if (other->id == row.id && (other->level == row.level || other->role != row.role)) return 0;
            }
            out->skills[out->skill_count++] = row;
        } else if (cells == 3 && !strcmp(cell[0], "D")) {
            int id;
            size_t type = 1;
            while (type < sizeof(defense_types) / sizeof(*defense_types) && strcmp(cell[2], defense_types[type]))
                type++;
            if (!cosmetic_ui_number(cell[1], &id) || !id || type == sizeof(defense_types) / sizeof(*defense_types))
                return 0;
            for (size_t i = 0; i < defense_count; ++i)
                if (defenses[i].id == id) return 0;
            defenses[defense_count++] = (CosmeticUiDefense){id, (int)type};
        } else if (cells == 3 && !strcmp(cell[0], "B")) {
            if (!*cell[1] || !cosmetic_ui_png_name(cell[2])) return 0;
            for (size_t i = 0; i < out->status_count; ++i)
                if (!strcmp(out->statuses[i].key, cell[1])) return 0;
            out->statuses[out->status_count++] = (CosmeticUiStatus){cell[1], cell[2]};
        } else if (cells == 2 && !strcmp(cell[0], "P")) {
            if (out->portrait || !cosmetic_ui_png_name(cell[1])) return 0;
            out->portrait = cell[1];
        } else if (cells == 2 && !strcmp(cell[0], "T")) {
            if (out->target || !cosmetic_ui_number(cell[1], &out->target) || !out->target) return 0;
        } else if (cells == 2 && !strcmp(cell[0], "A")) {
            static const char key_chars[] =
                "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-";
            size_t length = strlen(cell[1]);
            if (out->appearance || !length || length > 127 || strspn(cell[1], key_chars) != length) return 0;
            out->appearance = cell[1];
        } else return 0;
        line = next;
    }
    for (size_t i = 0; i < defense_count; ++i) {
        int found = 0;
        for (size_t j = 0; j < out->skill_count; ++j) {
            CosmeticUiSkill *skill = &out->skills[j];
            if (skill->id != defenses[i].id) continue;
            if (skill->role != COSMETIC_UI_DEFENSE) return 0;
            skill->defense_type = defenses[i].type;
            found = 1;
        }
        if (!found) return 0;
    }
    return 1;
}

static const char *cosmetic_ui_status(const CosmeticUiManifest *table, const char *key){
    for (size_t i = 0; i < table->status_count; ++i)
        if (!strcmp(table->statuses[i].key, key)) return table->statuses[i].png;
    return NULL;
}

static CosmeticUiFields cosmetic_ui_id_fields(const CosmeticUiManifest *table, int id,
                                               int level, int *found){
    CosmeticUiFields fields = {0};
    int text_level = -1, png_level = -1;
    *found = 0;
    if (level < 0) level = 0;
    for (size_t i = 0; i < table->skill_count; ++i) {
        const CosmeticUiSkill *row = &table->skills[i];
        if (row->id != id) continue;
        *found = 1;
        if (row->level > level) continue;
        if ((row->art.text || row->restore_name) && row->level > text_level) {
            fields.text = row->art.text;
            text_level = row->level;
        }
        if (row->art.png && row->level > png_level) {
            fields.png = row->art.png;
            png_level = row->level;
        }
    }
    return fields;
}

static int cosmetic_ui_exact(const CosmeticUiManifest *table, int id, int defense, int conditional){
    for (size_t i = 0; i < table->skill_count; ++i) {
        const CosmeticUiSkill *row = &table->skills[i];
        if (row->id != id) continue;
        if (row->role == COSMETIC_UI_UNKNOWN) return 1;
        int is_defense = row->role == COSMETIC_UI_DEFENSE;
        int is_attack = row->role >= COSMETIC_UI_ATTACK1 && row->role <= COSMETIC_UI_ATTACK3;
        return (defense < 0 || defense == is_defense) &&
               !(conditional == 1 && is_attack) &&
               !(conditional == 0 && row->role == COSMETIC_UI_CONDITIONAL);
    }
    return 0;
}

/* The displayed tier may be absent for a condition-driven move. The caller
   verifies that the observed action belongs to the covered unit and skill. */
static int cosmetic_ui_routed_tier(int displayed, int actual, int conditional){
    if (actual < 1 || actual > 3) return 0;
    if (displayed == actual || (!displayed && conditional == 1)) return actual;
    return 0;
}

/* Use the confirmed slot first. When multiple author skills share it, the
   observed coin count can disambiguate, but is not required for a unique match. */
static int cosmetic_ui_route_match(const CosmeticUiManifest *table, const ImportedAttackRoute *routes,
                                    int count, int source, int tier, int coins, int slot, int conditional){
    if (conditional < 0) return 0;
    int exact_source = 0, match = 0;
    for (int i = 0; i < count; ++i) {
        const ImportedAttackRoute *route = &routes[i];
        if (route->tier != tier || route->slot != slot || (coins && route->coins != coins)) continue;
        if (route->skill == source) exact_source = 1;
        int role = conditional ? COSMETIC_UI_CONDITIONAL : tier;
        for (size_t j = 0; j < table->skill_count; ++j) {
            const CosmeticUiSkill *row = &table->skills[j];
            if (row->id != route->skill || row->role != role) continue;
            if (match && match != route->skill) return 0;
            match = route->skill;
        }
    }
    return exact_source ? match : 0;
}

static int cosmetic_ui_route_id(const CosmeticUiManifest *table, const ImportedAttackRoute *routes,
                                 int count, int source, int tier, int coins, int slot, int conditional){
    int match = cosmetic_ui_route_match(table, routes, count, source, tier, 0, slot, conditional);
    if (!match && coins > 0)
        match = cosmetic_ui_route_match(table, routes, count, source, tier, coins, slot, conditional);
    return match;
}

static int cosmetic_ui_unique_role(const CosmeticUiManifest *table, int role){
    int match = 0;
    for (size_t i = 0; role && i < table->skill_count; ++i) {
        const CosmeticUiSkill *row = &table->skills[i];
        if (row->role != role) continue;
        if (match && match != row->id) return 0;
        match = row->id;
    }
    return match;
}

static int cosmetic_ui_mapped_id(const CosmeticUiManifest *table, int mapped, int defense, int conditional){
    return mapped && cosmetic_ui_exact(table, mapped, defense, conditional) ? mapped : 0;
}

static int cosmetic_ui_defense_skill(const CosmeticUiManifest *table, int source_id, int conditional, int *typed){
    const SrUiSkill *source = sr_ui_skill(source_id);
    int type = source && source->defense && conditional >= 0 ?
               source->defense + (conditional == 1 ? COSMETIC_UI_DERIVED_DEFENSE : 0) : 0;
    int match = 0, ambiguous = 0;
    *typed = 0;
    for (size_t i = 0; i < table->skill_count; ++i) {
        const CosmeticUiSkill *row = &table->skills[i];
        if (row->role != COSMETIC_UI_DEFENSE) continue;
        if (!row->defense_type) {
            ambiguous = 1;
            continue;
        }
        *typed = 1;
        if (row->defense_type == COSMETIC_UI_DERIVED_DEFENSE) continue;
        if (row->defense_type != type) continue;
        if (match && match != row->id) ambiguous = 1;
        match = row->id;
    }
    return ambiguous ? 0 : match;
}

static int cosmetic_ui_conditional_defense_mapped(const CosmeticUiManifest *table, int id, int mapped){
    const SrUiSkill *source = sr_ui_skill(id);
    const SrUiSkill *target = sr_ui_skill(mapped);
    if (!source || !source->defense || !target || target->defense != source->defense ||
        target->conditional != 1 || !cosmetic_ui_exact(table, mapped, 1, 1)) return 0;
    for (size_t i = 0; i < table->skill_count; ++i) {
        const CosmeticUiSkill *row = &table->skills[i];
        if (row->id != mapped) continue;
        return !row->defense_type || row->defense_type == COSMETIC_UI_DERIVED_DEFENSE ||
               row->defense_type == COSMETIC_UI_DERIVED_DEFENSE + source->defense;
    }
    return 0;
}

static CosmeticUiFields cosmetic_ui_author_fields(const CosmeticUiManifest *table, int id, int tier,
                                                   int defense, int conditional, int level, int routed,
                                                   int mapped){
    int found;
    if (cosmetic_ui_exact(table, id, defense, conditional))
        return cosmetic_ui_id_fields(table, id, level, &found);
    if (defense == 1) {
        int typed;
        if (conditional == 1 && cosmetic_ui_conditional_defense_mapped(table, id, mapped))
            return cosmetic_ui_id_fields(table, mapped, level, &found);
        int target = cosmetic_ui_defense_skill(table, id, conditional, &typed);
        if (typed || conditional == 1)
            return cosmetic_ui_id_fields(table, target, level, &found);
    }
    if (!routed) routed = cosmetic_ui_mapped_id(table, mapped, defense, conditional);
    if (routed) return cosmetic_ui_id_fields(table, routed, level, &found);
    int role = 0;
    if (conditional == 1 && defense == 0) role = COSMETIC_UI_CONDITIONAL;
    else if (defense == 1 && conditional != 1) role = COSMETIC_UI_DEFENSE;
    else if (defense == 0 && conditional == 0 && tier >= 1 && tier <= 3) role = tier;
    return cosmetic_ui_id_fields(table, cosmetic_ui_unique_role(table, role), level, &found);
}
#endif
