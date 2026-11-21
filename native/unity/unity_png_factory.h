#ifndef WEDGE_UNITY_PNG_FACTORY_H
#define WEDGE_UNITY_PNG_FACTORY_H
#include "wic_rgba.h"
#include "unity_raw_factory.h"
/* Decode once and synchronously upload; the WIC buffer is always released
   before return. Caller authenticates source and manages UrImage lifetime. */
static int up_create(const UrOps *ops,void *ctx,const UrMethods *methods,
                     const void *png,size_t length,int flip_vertical,
                     uint32_t expected_width,uint32_t expected_height,
                     float px,float py,float ppu,UrImage *out){
 if(!expected_width||!expected_height||!ops||!ops->is_unity_thread||!ops->is_unity_thread(ctx))return 0;
 WicRgba image={0};int ok=0;
 if(!wic_rgba_decode(png,length,&image))return 0;
 if(image.width!=expected_width||image.height!=expected_height||image.width>INT_MAX||image.height>INT_MAX)goto done;
 if(flip_vertical&&!wic_rgba_flip_vertical(&image))goto done;
 ok=ur_create(ops,ctx,methods,image.pixels,image.size,(int)image.width,(int)image.height,px,py,ppu,out);
done:
 wic_rgba_free(&image);return ok;
}
#endif
