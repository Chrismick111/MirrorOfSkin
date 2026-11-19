#include <assert.h>
#include "appearance_voice_catalog.h"
int main(void){
    assert(sr_voice_catalog_owner("10101_YiSang_BaseAppearance")==10101);
    assert(sr_voice_catalog_owner("story_10215_Faust_Ring_Disciple_CastOffAppearance")==10215);
    assert(sr_voice_catalog_owner("story_400003_QueenOfHatred")==400003);
    assert(sr_voice_catalog_owner("story_400003_QueenOfHatred_extra")==0);
    assert(sr_voice_catalog_audio(400003,"6SV-019-003"));
    assert(!sr_voice_catalog_audio(10101,"6SV-019-003"));
    assert(sr_voice_catalog_has_event(10101,"battle_endcommand"));
    assert(!sr_voice_catalog_has_event(10101,"battle_"));
    const char *key=sr_voice_catalog_event_key(10102,10101,"battle_endcommand_10102_1");
    assert(key && !strcmp(key,"battle_endcommand_10101_1"));
    assert(sr_voice_member_index(10101,key)>=0);
    int bubble=sr_voice_label_index("9SV-BAT4-03"); assert(bubble>=0 && sr_voice_labels[bubble].bubble);
    assert(!sr_voice_catalog_event_key(10102,10101,"battle_special_10102_1"));
    assert(!sr_voice_catalog_event_key(10102,10101,"battle_endcommand_10102_1-99"));
    assert(!sr_voice_catalog_event_key(10102,10101,"battle_endcommand_10102_99999999"));
    assert(!sr_voice_catalog_only_event(10101,"battle_endcommand"));
    return 0;
}
