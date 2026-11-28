#include "cosmetic_ui_rows.h"
#include "cosmetic_skill_catalog.h"
#include "unity_raw_factory.h"
#include "wic_rgba.h"

static _Thread_local int ur_in_canvas;
static int ur_actual_prepare(UrMethods *methods);
static const UrOps ur_actual_ops;
static void *method_by_types_one(void *klass,const char *name,const char **types,int count);
static int sr_method_is_static(void *method,void *declaring);
static int bind_addressable(const char *name,void *elementClass,void **out);

enum { COSMETIC_UI_MAX_LOOKS = 256, COSMETIC_UI_MAX_IMAGES = 128,
       COSMETIC_UI_MAX_STOCK = 256, COSMETIC_UI_MAX_PNG = 2 * 1024 * 1024 };
typedef struct {
    char look[64];
    wchar_t model[2048];
    char *bytes;
    CosmeticUiManifest *table;
    const char *appearance;
    struct CosmeticUiText *texts;
} CosmeticUiLook;
typedef struct CosmeticUiText {
    const char *utf8;
    void *text;
    uintptr_t root;
    struct CosmeticUiText *next;
} CosmeticUiText;
typedef struct {
    CosmeticUiLook *look;
    char png[69];
    UrImage image;
    int pending, attempts;
    DWORD retry_at;
} CosmeticUiImage;
typedef struct {
    int id, level, portrait, tried, loading, attempts;
    DWORD retry_at, started;
    void *text, *sprite, *operation;
    uintptr_t text_root, sprite_root, operation_root;
} CosmeticUiStock;

static CosmeticUiLook cosmetic_ui_looks[COSMETIC_UI_MAX_LOOKS];
static CosmeticUiImage cosmetic_ui_images[COSMETIC_UI_MAX_IMAGES];
static CosmeticUiStock cosmetic_ui_stock[COSMETIC_UI_MAX_STOCK];
static size_t cosmetic_ui_look_count, cosmetic_ui_image_count, cosmetic_ui_stock_count;
static void *cosmetic_ui_load_sprite, *cosmetic_ui_release_sprite;
static int cosmetic_ui_nonempty(const void *text);
static int cosmetic_ui_portrait_name(const char *name){
    return name && strlen(name) == 28 && !strcmp(name + 24, ".png") &&
           strspn(name, "0123456789abcdef") == 24;
}

static char *cosmetic_ui_read(wchar_t *path, DWORD limit, DWORD *length){
    if (!managed_bundle_file(path)) return NULL;
    HANDLE file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_DELETE, NULL,
                              OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, NULL);
    if (file == INVALID_HANDLE_VALUE) return NULL;
    BY_HANDLE_FILE_INFORMATION info;
    char *bytes = NULL;
    *length = 0;
    if (GetFileInformationByHandle(file, &info) &&
        !(info.dwFileAttributes & (FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT)) &&
        !info.nFileSizeHigh && info.nFileSizeLow && info.nFileSizeLow <= limit) {
        bytes = malloc((size_t)info.nFileSizeLow + 1);
        if (bytes && (!ReadFile(file, bytes, info.nFileSizeLow, length, NULL) || *length != info.nFileSizeLow)) {
            free(bytes);
            bytes = NULL;
        }
        if (bytes) bytes[*length] = 0;
    }
    CloseHandle(file);
    return bytes;
}

static int cosmetic_ui_adjacent(const CosmeticUiLook *look, const char *name, wchar_t path[2048]){
    wcscpy(path, look->model);
    wchar_t *slash = wcsrchr(path, L'\\');
    if (!slash) return 0;
    size_t cap = 2048 - (size_t)(slash + 1 - path);
    int written = swprintf(slash + 1, cap, L"%hs", name);
    return written > 0 && (size_t)written < cap;
}

static CosmeticUiLook *cosmetic_ui_import(const Skin *skin){
    /* Roland can be supplied by the bundled row or a managed external package.
       Only the selected model path can distinguish the two. */
    if (!skin->imported && (!skin->bundledPolicy || strcmp(skin->look, "BRolandBaseAppearance"))) return NULL;
    LocalArtForm *form = cached_art_form(skin->look);
    if (!form || !form->loadedPath || skin_local_policy(skin) != &form->config ||
        wcslen(form->loadedPath) >= 2048) return NULL;
    for (size_t i = 0; i < cosmetic_ui_look_count; ++i)
        if (!strcmp(cosmetic_ui_looks[i].look, skin->look) &&
            !_wcsicmp(cosmetic_ui_looks[i].model, form->loadedPath))
            return cosmetic_ui_looks[i].table ? &cosmetic_ui_looks[i] : NULL;
    if (cosmetic_ui_look_count == COSMETIC_UI_MAX_LOOKS) return NULL;
    CosmeticUiLook *look = &cosmetic_ui_looks[cosmetic_ui_look_count++];
    strcpy(look->look, skin->look);
    wcscpy(look->model, form->loadedPath);
    if (!imported_bundle_matches_loaded(skin->look, form->file, look->model)) return NULL;
    char name[96];
    snprintf(name, sizeof(name), "%s.skill-ui.tsv", skin->look);
    wchar_t path[2048];
    if (!cosmetic_ui_adjacent(look, name, path)) return NULL;
    DWORD bytes;
    char *data = cosmetic_ui_read(path, COSMETIC_UI_MAX_BYTES, &bytes);
    if (!data) return NULL;
    CosmeticUiManifest *table = calloc(1, sizeof(*table));
    if (!table || !MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, data, bytes, NULL, 0) ||
        !cosmetic_ui_parse(data, bytes, table)) {
        free(table);
        free(data);
        bootlog("cosmetic UI: rejected appearance sidecar");
        return NULL;
    }
    look->bytes = data;
    look->table = table;
    look->appearance = sr_ui_appearance_key(table->appearance);
    return look;
}

static void *cosmetic_ui_png(CosmeticUiLook *look, const char *png){
    if (!png) return NULL;
    for (size_t i = 0; i < cosmetic_ui_image_count; ++i) {
        CosmeticUiImage *entry = &cosmetic_ui_images[i];
        if (!strcmp(entry->png, png) && entry->look == look)
            return entry->image.sprite && rfield(entry->image.sprite, "m_CachedPtr") ? entry->image.sprite : NULL;
    }
    if (cosmetic_ui_image_count < COSMETIC_UI_MAX_IMAGES) {
        CosmeticUiImage *entry = &cosmetic_ui_images[cosmetic_ui_image_count++];
        entry->look = look;
        strcpy(entry->png, png);
        entry->pending = 1;
    }
    return NULL;
}

static void *cosmetic_ui_text(CosmeticUiLook *look, const char *utf8){
    if (!utf8) return NULL;
    for (CosmeticUiText *entry = look->texts; entry; entry = entry->next)
        if (entry->utf8 == utf8) return entry->text;
    CosmeticUiText *entry = malloc(sizeof(*entry));
    if (!entry) return NULL;
    entry->utf8 = utf8;
    entry->text = make_string(utf8);
    if (!cosmetic_ui_nonempty(entry->text)) entry->text = NULL;
    entry->root = ui_root(entry->text);
    if (entry->text && !entry->root) { free(entry); return NULL; }
    entry->next = look->texts;
    look->texts = entry;
    return entry->text;
}

static int cosmetic_ui_png_check(const unsigned char *bytes, DWORD size, const char *name){
    static const unsigned char header[] = {137,80,78,71,13,10,26,10,0,0,0,13,'I','H','D','R'};
    if (size < 33 || memcmp(bytes, header, sizeof(header))) return 0;
    for (int pos = 16; pos < 24; pos += 4) {
        unsigned width = ((unsigned)bytes[pos] << 24) | ((unsigned)bytes[pos + 1] << 16) |
                         ((unsigned)bytes[pos + 2] << 8) | bytes[pos + 3];
        if (!width || width > 512) return 0;
    }
    if (!name) return 1;
    BCRYPT_ALG_HANDLE algorithm = NULL;
    if (BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, NULL, 0) < 0) return 0;
    unsigned char digest[32];
    int ok = BCryptHash(algorithm, NULL, 0, (PUCHAR)bytes, size, digest, sizeof(digest)) >= 0;
    BCryptCloseAlgorithmProvider(algorithm, 0);
    const char *hex = "0123456789abcdef";
    for (size_t i = 0; ok && i < sizeof(digest); ++i)
        ok = name[2 * i] == hex[digest[i] >> 4] && name[2 * i + 1] == hex[digest[i] & 15];
    return ok;
}

static int cosmetic_ui_prepare_png(CosmeticUiImage *entry){
    static UrMethods methods;
    if (!methods.create && !ur_actual_prepare(&methods)) return 0;
    wchar_t path[32768];
    DWORD size;
    if (entry->look) {
        if (!cosmetic_ui_adjacent(entry->look, entry->png, path)) return 1;
    } else {
        if (!cosmetic_ui_portrait_name(entry->png)) return 1;
        wchar_t relative[96];
        swprintf(relative, 96, L"Workbench\\local_portraits\\%hs", entry->png);
        sr_data_path(g_self, path, 32768, relative);
        if (!*path) return 1;
    }
    char *bytes = cosmetic_ui_read(path, COSMETIC_UI_MAX_PNG, &size);
    if (!bytes) return 1;
    WicRgba rgba = {0};
    if (cosmetic_ui_png_check((unsigned char *)bytes, size, entry->look ? entry->png : NULL) &&
        wic_rgba_decode(bytes, size, &rgba) && rgba.width <= 512 && rgba.height <= 512 &&
        wic_rgba_flip_vertical(&rgba))
        ur_create(&ur_actual_ops, NULL, &methods, rgba.pixels, rgba.size,
                  (int)rgba.width, (int)rgba.height, 0.5f, 0.5f, 100, &entry->image);
    wic_rgba_free(&rgba);
    free(bytes);
    return 1;
}

static void *cosmetic_ui_class(void *image, const char *ns, const char *name){
    return ((void *(*)(void *,const char *,const char *))api[API_CLASS])(image, ns, name);
}

static void *cosmetic_ui_method(void *type, const char *name, const char **params, int count,
                                const char *ret, int is_static){
    for (void *c = type; c; c = ui_parent(c)) {
        void *method = method_by_types_one(c, name, params, count);
        if (method && team_returns(method, ret) && sr_method_is_static(method, c) == is_static)
            return method;
    }
    return NULL;
}

static void *cosmetic_ui_object(void *method, void *self, void **args){
    int ok = 0;
    void *result = call_obj(method, self, args, &ok);
    return ok ? result : NULL;
}

static int cosmetic_ui_nonempty(const void *text){
    if (!text) return 0;
    int length = *(const int *)((const char *)text + 16);
    const uint16_t *chars = (const uint16_t *)((const char *)text + 20);
    for (int i = 0; i < length; ++i) {
        uint16_t c = chars[i];
        if (c > 32 && c != 0x00a0 && c != 0x200b && c != 0x3000 && c != 0xfeff) return 1;
    }
    return 0;
}

static void *cosmetic_ui_static_data(int id, int portrait){
    static const char *i32[] = {"System.Int32"};
    void *manager = cosmetic_ui_class(g_game, "", "StaticDataManager");
    void *get_instance = cosmetic_ui_method(manager, "get_Instance", NULL, 0, "StaticDataManager", 1);
    if (!get_instance) get_instance = cosmetic_ui_method(manager, "get_Instance", NULL, 0, "T", 1);
    void *instance = cosmetic_ui_object(get_instance, NULL, NULL);
    if (!instance || ui_class(instance) != manager) return NULL;
    uintptr_t root = ui_root(instance);
    if (!root) return NULL;
    const char *name = portrait ? "get_PersonalityStaticDataList" : "get_SkillList";
    const char *ret = portrait ? "PersonalityStaticDataList" : "SkillStaticDataList";
    void *list = cosmetic_ui_object(cosmetic_ui_method(manager, name, NULL, 0, ret, 0), instance, NULL);
    uintptr_t list_root = ui_root(list);
    void *args[] = {&id};
    ret = portrait ? "PersonalityStaticData" : "SkillStaticData";
    void *data = list_root ? cosmetic_ui_object(cosmetic_ui_method(ui_class(list), "GetData", i32, 1, ret, 0),
                                                list, args) : NULL;
    ui_unroot(list_root);
    ui_unroot(root);
    return data;
}

/* Build the same addressable key type that the game uses for its skill icons. */
static void *cosmetic_ui_icon_key(void *icon){
    static const char *info_params[] = {"UIResourceType", "System.String"};
    static const char *key_params[] = {"System.String", "System.String", "System.Type", "System.Boolean"};
    void *builder = cosmetic_ui_class(g_game, "Addressable", "ResourceKeyBuilder");
    void *enum_type = cosmetic_ui_class(g_game, "", "UIResourceType");
    void *field = enum_type ? ((void *(*)(void *,const char *))api[API_FIELD])(enum_type, "SkillIcon") : NULL;
    void *boxed = field ? ((void *(*)(void *,void *))api[API_FIELD_VALUE])(field, NULL) : NULL;
    uintptr_t enum_root = ui_root(boxed);
    void *enum_value = enum_root ? ui_unbox(boxed) : NULL;
    void *info_args[] = {enum_value, icon};
    void *info = enum_value ? cosmetic_ui_object(cosmetic_ui_method(builder, "BuildUIResourceKeyInfo", info_params, 2,
                                                                    "Addressable.KeyInfo", 1), NULL, info_args) : NULL;
    uintptr_t info_root = ui_root(info);
    ui_unroot(enum_root);
    if (!info_root) return NULL;
    void *sprite_type = cosmetic_ui_class(g_core, "UnityEngine", "Sprite");
    void *type = sprite_type ? ((void *(*)(void *))api[API_TYPE_OBJECT])(
                    ((void *(*)(void *))api[API_CLASS_TYPE])(sprite_type)) : NULL;
    uintptr_t type_root = ui_root(type);
    uint8_t alternative = 0;
    void *args[] = {rfield(info, "label"), rfield(info, "resourceId"), type, &alternative};
    void *key = type_root && args[0] && args[1] ? cosmetic_ui_object(cosmetic_ui_method(builder, "BuildKey", key_params, 4,
                                                                                       "System.String", 1), NULL, args) : NULL;
    ui_unroot(type_root);
    ui_unroot(info_root);
    return key;
}

static int cosmetic_ui_start_stock(CosmeticUiStock *entry){
    static const char *i32[] = {"System.Int32"};
    void *data = cosmetic_ui_static_data(entry->id, entry->portrait);
    uintptr_t root = ui_root(data);
    if (!root) return 0;
    void *type = ui_class(data);
    if (entry->portrait) {
        void *portrait = cosmetic_ui_method(type, "GetPortraitSprite", NULL, 0, "UnityEngine.Sprite", 0);
        entry->sprite = cosmetic_ui_object(portrait, data, NULL);
        entry->sprite_root = ui_root(entry->sprite);
        if (!entry->sprite_root) entry->sprite = NULL;
    } else {
        void *args[] = {&entry->level};
        void *name = cosmetic_ui_method(type, "GetSkillName", i32, 1, "System.String", 0);
        void *text = cosmetic_ui_object(name, data, args);
        entry->text = cosmetic_ui_nonempty(text) ? text : NULL;
        entry->text_root = ui_root(entry->text);
        if (!entry->text_root) entry->text = NULL;
        void *get_icon = cosmetic_ui_method(type, "GetIconID", i32, 1, "System.String", 0);
        void *icon = cosmetic_ui_object(get_icon, data, args);
        uintptr_t icon_root = cosmetic_ui_nonempty(icon) ? ui_root(icon) : 0;
        if (icon_root) {
            void *sprite = cosmetic_ui_class(g_core, "UnityEngine", "Sprite");
            if (!cosmetic_ui_release_sprite && sprite)
                bind_addressable("Release", sprite, &cosmetic_ui_release_sprite);
            if (!cosmetic_ui_load_sprite && cosmetic_ui_release_sprite)
                bind_addressable("LoadAssetAsync", sprite, &cosmetic_ui_load_sprite);
            void *key = cosmetic_ui_load_sprite ? cosmetic_ui_icon_key(icon) : NULL;
            uintptr_t key_root = ui_root(key);
            if (key_root) {
                void *key_args[] = {key};
                entry->operation = cosmetic_ui_object(cosmetic_ui_load_sprite, NULL, key_args);
                entry->operation_root = ui_root(entry->operation);
                entry->loading = entry->operation_root != 0;
                entry->started = GetTickCount();
                if (entry->operation && !entry->operation_root) {
                    void *release_args[] = {ui_unbox(entry->operation)};
                    call_exc(cosmetic_ui_release_sprite, NULL, release_args);
                    entry->operation = NULL;
                }
            }
            ui_unroot(key_root);
        }
        ui_unroot(icon_root);
    }
    ui_unroot(root);
    return 1;
}

static CosmeticUiStock *cosmetic_ui_stock_entry(int id, int level, int portrait){
    if (id <= 0) return NULL;
    if (level < 1) level = 1;
    for (size_t i = 0; i < cosmetic_ui_stock_count; ++i) {
        CosmeticUiStock *entry = &cosmetic_ui_stock[i];
        if (entry->id == id && entry->level == level && entry->portrait == portrait) return entry;
    }
    if (cosmetic_ui_stock_count == COSMETIC_UI_MAX_STOCK) return NULL;
    CosmeticUiStock *entry = &cosmetic_ui_stock[cosmetic_ui_stock_count++];
    *entry = (CosmeticUiStock){.id = id, .level = level, .portrait = portrait};
    return entry;
}

static int cosmetic_ui_release_operation(CosmeticUiStock *entry){
    if (!entry->operation) return 1;
    void *args[] = {ui_unbox(entry->operation)};
    if (!call_exc(cosmetic_ui_release_sprite, NULL, args)) return 0;
    ui_unroot(entry->operation_root);
    entry->operation = NULL;
    entry->operation_root = 0;
    return 1;
}

static void cosmetic_ui_data_pump(void){
    if (!ur_in_canvas || g_quitting) return;
    DWORD now = GetTickCount();
    for (size_t i = 0; i < cosmetic_ui_image_count; ++i) {
        CosmeticUiImage *entry = &cosmetic_ui_images[i];
        if (!entry->pending || (entry->attempts && (LONG)(now - entry->retry_at) < 0)) continue;
        entry->pending = !cosmetic_ui_prepare_png(entry) && ++entry->attempts < 3;
        entry->retry_at = now + 1000;
        break;
    }
    int waiting = 0;
    for (size_t i = 0; i < cosmetic_ui_stock_count; ++i) {
        CosmeticUiStock *entry = &cosmetic_ui_stock[i];
        if (!entry->loading) continue;
        void *type = ui_class(entry->operation), *handle = ui_unbox(entry->operation);
        int done = call_bool(find_method(type, "get_IsDone", 0), handle, NULL);
        if (!done && now - entry->started < 15000) { ++waiting; continue; }
        entry->loading = 0;
        if (done == 1 && call_int(find_method(type, "get_Status", 0), handle, NULL) == 1)
            entry->sprite = cosmetic_ui_object(find_method(type, "get_Result", 0), handle, NULL);
        if (!entry->sprite) cosmetic_ui_release_operation(entry);
    }
    if (waiting >= 4) return;
    for (size_t i = 0; i < cosmetic_ui_stock_count; ++i) {
        CosmeticUiStock *entry = &cosmetic_ui_stock[i];
        if (entry->tried || (entry->attempts && (LONG)(now - entry->retry_at) < 0)) continue;
        entry->tried = cosmetic_ui_start_stock(entry) || ++entry->attempts >= 3;
        entry->retry_at = now + 1000;
        break;
    }
}

static void cosmetic_ui_data_clear(void){
    if (!ur_in_canvas || g_quitting) return;
    for (size_t i = 0; i < cosmetic_ui_image_count; ++i) {
        CosmeticUiImage *entry = &cosmetic_ui_images[i];
        entry->pending = 0;
        if (ur_release(&ur_actual_ops, NULL, &entry->image))
            memset(entry, 0, sizeof(*entry));
    }
    for (size_t i = 0; i < cosmetic_ui_stock_count; ++i) {
        CosmeticUiStock *entry = &cosmetic_ui_stock[i];
        if (!cosmetic_ui_release_operation(entry)) continue;
        ui_unroot(entry->sprite_root);
        ui_unroot(entry->text_root);
        memset(entry, 0, sizeof(*entry));
    }
    size_t images = 0, stock = 0;
    for (size_t i = 0; i < cosmetic_ui_image_count; ++i)
        if (cosmetic_ui_images[i].png[0]) cosmetic_ui_images[images++] = cosmetic_ui_images[i];
    for (size_t i = 0; i < cosmetic_ui_stock_count; ++i)
        if (cosmetic_ui_stock[i].id) cosmetic_ui_stock[stock++] = cosmetic_ui_stock[i];
    cosmetic_ui_stock_count = stock;
    cosmetic_ui_image_count = images;
    if (images) return;
    for (size_t i = 0; i < cosmetic_ui_look_count; ++i) {
        CosmeticUiLook *look = &cosmetic_ui_looks[i];
        while (look->texts) {
            CosmeticUiText *text = look->texts;
            look->texts = text->next;
            ui_unroot(text->root);
            free(text);
        }
        free(look->table);
        free(look->bytes);
        memset(look, 0, sizeof(*look));
    }
    cosmetic_ui_look_count = 0;
}

static int cosmetic_ui_live_route_tier(Unit *u, const Skin *skin, int skill_id,
                                       int tier, int defense, int conditional){
    if (defense || conditional < 0 || !skin->imported || !u->viewerActive || !u->observedAction ||
        !skin->importedRouteValid || skin->importedRouteSkill != skill_id ||
        skin->importedRouteSlot < 0 ||
        observed_skill_id(u, u->observedAction, 1) != skill_id) return 0;
    return cosmetic_ui_routed_tier(tier, skin->importedRouteTier, conditional);
}

static const char *cosmetic_ui_workbench_portrait(const PoolRow *row, const char *look){
    char story[72];
    snprintf(story, sizeof(story), "story_%s", look);
    const char *png = sr_cosmetic_cached_portrait(story);
    if (!png && !strcmp(row->appearance_name, look)) png = sr_cosmetic_cached_portrait(row->identity);
    return cosmetic_ui_portrait_name(png) ? png : NULL;
}

static int cosmetic_ui_resolve(Unit *u, int skill_id, int tier, int defense, int conditional,
                               int level, const char *status_key, int portrait,
                               void **new_text, void **new_sprite){
    *new_text = NULL;
    *new_sprite = NULL;
    if (!ur_in_canvas || !enabled_now() || cleanup_pending || g_quitting) return 0;
    Skin *skin = voice_worn_skin(u);
    if (!skin) return 0;
    CosmeticUiLook *look = cosmetic_ui_import(skin);
    const PoolRow *row = &g_rows[skin->row];
    const char *identity = row->identity;
    int stock_id = 0;
    if (portrait) {
        if (look) *new_sprite = cosmetic_ui_png(look, look->table->portrait);
        if (!look && !skin->imported) {
            stock_id = sr_cosmetic_stock_portrait(identity, skin->look);
            if (!stock_id) *new_sprite = cosmetic_ui_png(NULL, cosmetic_ui_workbench_portrait(row, skin->look));
        }
    } else if (status_key && *status_key) {
        if (look) *new_sprite = cosmetic_ui_png(look, cosmetic_ui_status(look->table, status_key));
    } else if (skill_id > 0) {
        const SrUiSkill *source = sr_ui_skill(skill_id);
        if (source) {
            if (source->conditional == 1 || conditional < 0) conditional = source->conditional;
            if (defense < 0) defense = source->defense != 0;
            if (!tier && source->tier >= 1 && source->tier <= 3) tier = source->tier;
        }
        if (look) {
            CosmeticUiManifest *table = look->table;
            char target[16];
            snprintf(target, sizeof(target), "%d", table->target);
            int mapped = defense >= 0 ?
                sr_cosmetic_stock_display_skill(target, look->appearance, skill_id, tier, defense, conditional) : 0;
            int routed = 0;
            int actual_tier = cosmetic_ui_exact(table, skill_id, defense, conditional) ? 0 :
                              cosmetic_ui_live_route_tier(u, skin, skill_id, tier, defense, conditional);
            if (actual_tier) {
                const ImportedConfig *config = skin->imported;
                routed = cosmetic_ui_route_id(table, config->routes, config->routeCount, skill_id, actual_tier,
                                              skin->importedRouteCoins, skin->importedRouteSlot, conditional);
            }
            CosmeticUiFields art =
                cosmetic_ui_author_fields(table, skill_id, tier, defense, conditional, level, routed, mapped);
            *new_text = cosmetic_ui_text(look, art.text);
            *new_sprite = cosmetic_ui_png(look, art.png);
            return *new_text || *new_sprite;
        } else if (!skin->imported && defense >= 0) {
            stock_id = sr_cosmetic_stock_display_skill(identity, skin->look, skill_id, tier, defense, conditional);
        }
    }
    if (stock_id && !*new_sprite) {
        CosmeticUiStock *stock = cosmetic_ui_stock_entry(stock_id, portrait ? 1 : level, portrait);
        if (stock) {
            if (!portrait) *new_text = stock->text;
            if (!*new_sprite && stock->sprite && rfield(stock->sprite, "m_CachedPtr")) *new_sprite = stock->sprite;
            if (portrait && stock->tried && !*new_sprite)
                *new_sprite = cosmetic_ui_png(NULL, cosmetic_ui_workbench_portrait(row, skin->look));
        }
    }
    return *new_text || *new_sprite;
}
