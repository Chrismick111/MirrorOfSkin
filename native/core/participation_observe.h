#ifndef PARTICIPATION_OBSERVE_H
#define PARTICIPATION_OBSERVE_H
#include <stdint.h>
typedef uint8_t (*ParticipationCall)(void *);
typedef void (*ParticipationLog)(void *,uint8_t);
static uint8_t participation_run(void *ctx,int enabled,ParticipationCall call,ParticipationLog log){uint8_t result=call(ctx);if(enabled)log(ctx,result);return result;}
#endif
